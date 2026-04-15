# Admin Frontend Integration Guide

This document outlines the frontend integration details for the Admin features within the Lecture Brain platform. It covers authentication, available endpoints, data structures, and examples using `axios`.

## 1. Authentication & Authorization

All `/admin/*` endpoints strictly require an administrator account. 

To authenticate, you must include the JWT token in the `Authorization` header of your requests:
```http
Authorization: Bearer <your_jwt_token>
```
*Note: Ensure your authenticated user has the necessary 'Admin' privileges. If not, the server will reject the request with a **403 Forbidden** error.*

## 2. Admin Endpoints

### 2.1 Get Subject Analytics
**`GET /admin/analytics`**

Retrieves the most recent AI-generated analytics dashboard data across all subjects. This highlights areas where students are struggling and providing AI-generated insights for teachers.

**Response Structure (JSON Array):**
```json
[
  {
    "subject_id": "60d5ecb8b311f93f54bd4c8a",
    "subject_name": "System Architecture",
    "weak_topics": [
      {
        "topic": "Microservices",
        "frequency_score": 15
      }
    ],
    "common_questions": [
      "How does saga pattern work?"
    ],
    "confusing_concepts": [
      "Eventual consistency"
    ],
    "engagement_count": 120,
    "ai_insight": "Students are consistently struggling with distributed transactions. Consider dedicating more time to this in the next lecture.",
    "last_analyzed_at": "2026-04-14T15:00:00Z"
  }
]
```

**Axios Implementation Snippet:**
```javascript
import axios from 'axios';

const getAnalytics = async (token) => {
  try {
    const response = await axios.get('/admin/analytics', {
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.data;
  } catch (error) {
    console.error("Failed to fetch analytics:", error);
    throw error;
  }
};
```

### 2.2 Get Lecture Operations Monitoring
**`GET /admin/operations`**

This endpoint returns the processing status of all uploaded lectures for dashboard observability. It is intended to be polled periodically by the frontend.

**Response Structure (JSON Array):**
```json
[
  {
    "lecture_id": "60d5ec49b311f93f54bd4c8f",
    "title": "Week 1: Introduction to Distributed Systems",
    "status": "processing",
    "job_tracker": {
      "upload_status": "completed",
      "extraction_status": "completed",
      "chunking_status": "in_progress",
      "embedding_status": "pending",
      "card_generation_status": "pending",
      "error_traceback": null
    },
    "created_at": "2026-04-14T14:30:00Z"
  }
]
```

**`job_tracker` Object Fields Clarification:**
Instead of generic `status`/`progress` fields, the data processing pipeline is broken down into specific granular phases, matching our actual endpoint schema:
- `upload_status`: File saved successfully.
- `extraction_status`: Extracting text/audio out of the document/video.
- `chunking_status`: Breaking down content into optimal LLM token sizes.
- `embedding_status`: Vectorizing the content for RAG.
- `card_generation_status`: Auto-generating flashcards.
- `error_traceback`: Contains detailed stack traces if a specific pipeline stage fails (`null` if healthy).

**Axios Implementation Snippet (with simple polling):**
```javascript
import axios from 'axios';

const pollOperations = async (token) => {
  try {
    const response = await axios.get('/admin/operations', {
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.data; // Array of Lecture tracking objects
  } catch (error) {
    console.error("Failed to fetch operations:", error);
    throw error;
  }
};

// Example Polling usage:
// setInterval(() => pollOperations(userToken), 5000);
```

### 2.3 Managing Data (Operations)

Below is the management endpoint for forcing an analytics re-index/generation.

#### Trigger Analytics Re-index
**`POST /admin/analytics/generate`**

Manually triggers batch LLM analysis of all unanalyzed chat logs across all subjects. Useful to force a dashboard refresh to pick up the latest student interactions.

**Request Body:** None required.

**Example Response:**
```json
{
  "subjects_processed": 5,
  "total_messages_analyzed": 142,
  "message": "Analytics successfully generated and updated."
}
```

**Axios Implementation Snippet:**
```javascript
import axios from 'axios';

const triggerAnalytics = async (token) => {
  try {
    const response = await axios.post('/admin/analytics/generate', {}, {
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.data;
  } catch (error) {
    console.error("Failed to trigger analytics generation:", error);
    throw error;
  }
};
```

*(Note: Additional POST routes exist for `/admin/upload_pdf` and `/admin/upload_video` using `multipart/form-data` and JSON bodies respectively.)*

## 3. Error Handling

When interacting with the `/admin` prefix endpoints, pay special attention to the following standard HTTP errors:

*   **`403 Forbidden`**: This signifies a permissions error. It means the JWT token sent in the headers belongs to a valid user, but that user does NOT have Administrator privileges. The frontend UI should handle this by gracefully denying access or redirecting them to a standard user dashboard/login.
*   **`404 Not Found`**: Typically returned when attempting an operation on an asset that does not exist in the context of an admin action. For example, trying to upload details to a `lecture_id` that is mathematically invalid or has been deleted from the database.
*   **`401 Unauthorized`**: Sent if no valid token was provided at all, or if the token itself has expired or is cryptographically invalid.
