# Lecture Brain — Frontend API Integration Guide

Welcome to the Lecture Brain API! This guide covers exactly how to authenticate, format your requests, and consume the core endpoints.

## 🌍 1. Base Configuration

### Base URL
If deployed on Railway, your base URL will look something like this:
```
https://lecture-brain-production.up.railway.app
```
*(Replace this with your actual Railway deployment URL).*

### CORS Policy
**Confirmed:** The backend is currently configured with `allow_origins=["*"]`. You will not face CORS issues during development, and requests from `localhost` or your frontend deployment domain will succeed natively.

---

## 🔐 2. Authentication Flow

The API uses standard **JWT (JSON Web Tokens)**. Every protected endpoint requires the token to be passed in the HTTP `Authorization` header like this:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5c...
```

### Getting the Token (The Login Endpoint)

> **WARNING:** The login endpoint does **NOT** accept JSON. It strictly requires `application/x-www-form-urlencoded` (Standard Form Data). Furthermore, the field name for the email must be exactly `username`.

**Endpoint:** `POST /auth/login`
**Content-Type:** `application/x-www-form-urlencoded`

**Request Example (JavaScript/Axios):**
```javascript
const formData = new URLSearchParams();
formData.append('username', 'student@example.com'); // IMPORTANT: must be 'username', not 'email'
formData.append('password', 'secret123');

const response = await axios.post('https://<RAILWAY_URL>/auth/login', formData, {
  headers: {
    'Content-Type': 'application/x-www-form-urlencoded'
  }
});
```

**Success Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJI...",
  "token_type": "bearer"
}
```
*Save the `access_token` in `localStorage` or secure cookies to use in subsequent requests.*

---

## 📤 3. Core Endpoint Examples

### A. Register a New User
**Endpoint:** `POST /auth/register`
**Content-Type:** `application/json`

**Request Body:**
```json
{
  "email": "student@example.com",
  "password": "strongpassword123"
}
```

**Success Response (201 Created):**
```json
{
  "id": "60d5ec49e...",
  "email": "student@example.com",
  "is_active": true
}
```

---

### B. Create a Subject & Lecture
Before uploading files, you must create a Subject and a Lecture container.

**Endpoint:** `POST /subjects/`
**Headers:** `Authorization: Bearer <token>`
**Request Body:**
```json
{
  "name": "Machine Learning 101",
  "description": "Introductory ML course"
}
```

*Extract the returned `id` (e.g., `subject_id`).*

**Endpoint:** `POST /lectures/`
**Headers:** `Authorization: Bearer <token>`
**Request Body:**
```json
{
  "title": "Week 1: Linear Regression",
  "description": "Math foundations",
  "subject_id": "<subject_id_from_above>"
}
```

*Extract the returned `id` (this is your `lecture_id`).*

---

### C. Upload a File (PDF)
> **IMPORTANT:** File uploads require `multipart/form-data`.

**Endpoint:** `POST /knowledge/upload_pdf/{lecture_id}`
**Headers:**
- `Authorization: Bearer <token>`
- `Content-Type: multipart/form-data`

**Request Example (JavaScript/Axios):**
```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]); // The actual File object

const response = await axios.post(
  `https://<RAILWAY_URL>/knowledge/upload_pdf/${lecture_id}`, 
  formData,
  {
    headers: {
      'Authorization': `Bearer ${token}`
      // Axios sets multipart/form-data boundary automatically
    }
  }
);
```

**Success Response (200 OK):**
```json
{
  "filename": "lecture_slides.pdf",
  "lecture_id": "60d5ec49e...",
  "status": "processing",
  "message": "PDF upload successful, processing started in background"
}
```
*(You can poll `GET /lectures/{lecture_id}/status` to check when processing is complete).*

---

### D. Chat with the AI
**Endpoint:** `POST /ai/chat`
**Headers:** 
- `Authorization: Bearer <token>`
- `Content-Type: application/json`

**Request Body:**
```json
{
  "message": "Can you explain how gradient descent works based on this lecture?",
  "lecture_id": "<lecture_id>",
  "history": [
    {"role": "user", "content": "What is the main topic?"},
    {"role": "assistant", "content": "The main topic is Linear Regression."}
  ]
}
```

**Success Response (200 OK):**
```json
{
  "answer": "Gradient descent is described on slide 4 as an optimization algorithm...",
  "sources": [
    "Page 4 (Similarity: 0.89)"
  ]
}
```

---

## 🛠️ Summary FAQ for Frontend Devs

1. **Why am I getting a 422 Unprocessable Entity on Login?**
   You are likely sending a JSON body (`{ "email": "..." }`). You **must** send Form Data natively with the key `username`.
2. **Why am I getting a 401 Unauthorized elsewhere?**
   Ensure your header string is exactly `"Bearer <token>"`. Do not forget the space between "Bearer" and the token.
3. **Is it normal for the AI endpoints to take a few seconds?**
   Yes. `POST /ai/chat` performs database Vector Searches and syncs with OpenAI's GPT-4. Show a loading spinner in the UI while waiting for the response!
