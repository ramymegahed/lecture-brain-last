import asyncio
import sys
import os

sys.path.append('.') # So we can import app

from app.database.mongodb import init_db, close_db
from app.models.user import User
from app.models.subject import Subject
from app.models.lecture import Lecture, LectureSource
from app.models.knowledge import KnowledgeChunk
from app.models.knowledge_card import KnowledgeCard
from app.knowledge.video_processor import process_video_background

async def run_test():
    print("--- Starting Video Pipeline End-to-End Test ---")
    await init_db()
    print("[1] Database initialized.")

    # Clean up any previous failed tests so we don't pollute
    await User.find({"email": "test_e2e_video@example.com"}).delete()
    
    # Create dummy User
    user = User(email="test_e2e_video@example.com", hashed_password="pw", name="Tester", is_active=True, role="user")
    await user.insert()
    
    # Create dummy Subject
    subject = Subject(name="Test End2End Video", description="Testing video pipeline", owner=user)
    await subject.insert()
    
    video_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw" # 18 sec video "Me at the zoo"
    
    # Create dummy Lecture
    source = LectureSource(type="video", url=video_url, status="processing")
    lecture = Lecture(title="Test Video Pipeline", subject=subject, sources=[source])
    await lecture.insert()
    
    print(f"[2] Test Lecture created (ID: {lecture.id}). Initial Status: {lecture.status}")
    print(f"    JobTracker initial: {lecture.job_tracker}")
    
    print(f"[3] Triggering background process with URL: {video_url}...")
    task = asyncio.create_task(process_video_background(str(lecture.id), video_url))
    
    print("[4] Polling database status:")
    last_status = None
    last_tracker = None
    
    while not task.done():
        l = await Lecture.get(lecture.id)
        current_status = l.status
        current_tracker = l.job_tracker.model_dump()
        
        if current_status != last_status or current_tracker != last_tracker:
            print(f"  -> State Shift! Status: {current_status}")
            print(f"     Tracker: {current_tracker}")
            last_status = current_status
            last_tracker = current_tracker
        
        await asyncio.sleep(0.5)
        
    await task
    
    print("[5] Background process returned.")
    
    # Final Validation
    print("\n--- Data Integrity Check ---")
    l = await Lecture.get(lecture.id)
    print(f"Final Status: {l.status}")
    print(f"Final JobTracker: {l.job_tracker.model_dump()}")
    
    if l.status != "completed":
        print(f"WARNING: Job status is {l.status}, expected 'completed'")
    
    chunks = await KnowledgeChunk.find({"lecture_id": str(lecture.id)}).to_list()
    print(f"Knowledge Chunks generated: {len(chunks)}")
    
    card = await KnowledgeCard.find_one({"lecture.$id": lecture.id})
    if card:
        print(f"Knowledge Card generated! Summary:\n  {card.summary}")
    else:
        print("Knowledge Card NOT generated!")
        print(f"Did trying to query by lecture.$id={lecture.id} fail?")
        
    print("\n[6] Cleaning up...")
    
    await KnowledgeChunk.find({"lecture_id": str(lecture.id)}).delete()
    if card:
        await card.delete()
    await lecture.delete()
    await subject.delete()
    await user.delete()
    
    await close_db()
    print("Cleanup complete.")

if __name__ == "__main__":
    asyncio.run(run_test())
