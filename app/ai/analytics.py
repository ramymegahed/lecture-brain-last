import json
from datetime import datetime, timezone
from beanie import PydanticObjectId
from app.core.clients import openai_client
from app.models.subject import Subject
from app.models.chat_log import ChatLog
from app.models.subject_analytics import SubjectAnalytics, WeakTopic
from app.ai.prompts import SYSTEM_PROMPT_ANALYTICS

BATCH_LIMIT = 200

async def generate_subject_analytics() -> dict:
    """
    Triggers batch analysis for all subjects with unanalyzed chat logs.
    Returns a summary of the generation process.
    """
    subjects = await Subject.find_all().to_list()
    
    total_messages_analyzed = 0
    subjects_processed = 0
    
    for subject in subjects:
        subject_id = str(subject.id)
        
        # 1. Fetch unanalyzed chat logs for this subject
        logs = await ChatLog.find(
            ChatLog.analyzed == False,
            ChatLog.subject_id == subject_id
        ).limit(BATCH_LIMIT).to_list()
        
        if not logs:
            continue
            
        logs_count = len(logs)
        
        # 2. Fetch existing analytics if available
        existing_analytics_doc = await SubjectAnalytics.find_one(SubjectAnalytics.subject_id == subject_id)
        existing_analytics_str = "No prior analytics."
        
        if existing_analytics_doc:
            existing_analytics_str = json.dumps({
                "weak_topics": [t.model_dump() for t in existing_analytics_doc.weak_topics],
                "common_questions": existing_analytics_doc.common_questions,
                "confusing_concepts": existing_analytics_doc.confusing_concepts,
                "ai_insight": existing_analytics_doc.ai_insight
            }, indent=2)
            
        # 3. Format new questions
        new_questions_str = ""
        for i, log in enumerate(logs):
            new_questions_str += f"[{i+1}] Q: {log.question}\n"
            
        # 4. Prompt LLM
        prompt = SYSTEM_PROMPT_ANALYTICS.format(
            subject_name=subject.name,
            existing_analytics=existing_analytics_str,
            new_questions=new_questions_str
        )
        
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": prompt}],
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        
        try:
            parsed = json.loads(content)
            
            # Remove markdown JSON wrappers if present
            if isinstance(parsed, str):
                parsed = json.loads(parsed.strip("```json").strip("```").strip())
                
        except Exception as e:
            print(f"Error parsing JSON from analytics LLM: {e}")
            continue

        # 5. Save new SubjectAnalytics
        new_topics = [WeakTopic(**t) for t in parsed.get("weak_topics", [])]
        
        engagement_count = logs_count
        if existing_analytics_doc:
            engagement_count += existing_analytics_doc.engagement_count
            
        if existing_analytics_doc:
            existing_analytics_doc.weak_topics = new_topics
            existing_analytics_doc.common_questions = parsed.get("common_questions", [])
            existing_analytics_doc.confusing_concepts = parsed.get("confusing_concepts", [])
            existing_analytics_doc.ai_insight = parsed.get("ai_insight", "")
            existing_analytics_doc.engagement_count = engagement_count
            existing_analytics_doc.last_analyzed_at = datetime.now(timezone.utc)
            await existing_analytics_doc.save()
        else:
            new_analytics = SubjectAnalytics(
                subject=subject,
                subject_id=subject_id,
                subject_name=subject.name,
                weak_topics=new_topics,
                common_questions=parsed.get("common_questions", []),
                confusing_concepts=parsed.get("confusing_concepts", []),
                engagement_count=engagement_count,
                ai_insight=parsed.get("ai_insight", "")
            )
            await new_analytics.insert()
            
        # 6. Mark logs as analyzed
        log_ids = [log.id for log in logs]
        await ChatLog.find({"_id": {"$in": log_ids}}).update({"$set": {"analyzed": True}})
        
        total_messages_analyzed += logs_count
        subjects_processed += 1
        
    return {
        "subjects_processed": subjects_processed,
        "total_messages_analyzed": total_messages_analyzed,
        "message": "Analytics batch complete."
    }
