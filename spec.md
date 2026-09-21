# AI Chemistry Video Generation Backend

## 1. Overview
This document specifies the design and architecture for an AI-native backend service that generates short educational chemistry videos. The system allows clients to submit requests for chemistry concepts, processes these requests asynchronously using an AI pipeline and Manim, and exposes endpoints to track the job status and retrieve the final video artifact.

## 2. Product Requirements
*   **Format:** Short educational video (TikTok/YouTube Shorts style), vertical 9:16 aspect ratio, duration < 3 minutes.
*   **Scope:** Specifically handles chemistry concepts. The MVP must support:
    1.  *How does the pH scale work?*
    2.  *Why do atoms form covalent bonds?*
    3.  *What is the difference between ionic and covalent bonding?*
*   **Reliability:** The system must handle LLM non-determinism gracefully through validation, retries, and clear failure states.

## 3. Technology Stack
*   **Backend Framework:** Python + FastAPI
*   **Video Engine:** Manim Community Edition
    *   All visual content — chemical formulas, molecular structures, diagrams, animations — is rendered directly by Manim using LaTeX and built-in geometry primitives.
    *   No external image generation API is used. This simplifies the pipeline, removes a network dependency, and guarantees visual consistency across runs.
*   **Asynchronous Queue:** FastAPI BackgroundTasks (MVP); upgradeable to Celery + Redis
*   **AI Services (Free Tier):**
    *   LLM: Google Gemini (script generation + Manim code generation)
    *   TTS: Edge TTS (voiceover narration)


## 4. System Architecture & User Flow

### 4.1. Request Flow
1.  **Submit Request:** Client calls the API with a prompt (e.g., "Explain covalent bonds").
2.  **Queueing:** The backend creates a Job with status `WAITING` and puts it in the async queue, returning the `job_id` to the client.
3.  **Processing:** A worker picks up the Job, changing its status to `PROCESSING`.
4.  **AI Pipeline Execution:** The worker runs the generation pipeline (details below).
5.  **Completion:** Upon success, the status is set to `COMPLETED`, and the video path is saved. If it fails, the status is set to `FAILED` with a detailed reason.
6.  **Retrieval:** Client polls the job status and downloads the video when `COMPLETED`.

### 4.2. AI Pipeline Steps
To ensure reliability against non-determinism, the generation is broken into deterministic steps with validation:

*   **Step 0: Validation (`validate_prompt`)**
    *   Uses an LLM or keyword rules to check if the prompt is chemistry-related and within the supported scope.
    *   *Failure State:* If rejected, the job immediately fails with reason "Prompt is not related to supported chemistry topics."
*   **Step 1: Script Generation (`gen_scripts`)**
    *   LLM generates a structured JSON response containing the voiceover script broken into scenes, and visual directions for each scene.
*   **Step 2: Voiceover Generation (`gen_speech`)**
    *   Pass the script to a TTS engine to generate `.wav` or `.mp3` files. Calculate audio duration for syncing Manim animations.
*   **Step 3: Manim Code Generation (`gen_code`)**
    *   LLM generates Manim Python code based on the script, visual directions, and audio timings.
    *   *Guardrail:* Provide the LLM with a strict Manim template and examples of correct syntax.
*   **Step 4: Code Validation & Rendering (The "Retry Loop")**
    *   Execute the Manim code in an isolated subprocess.
    *   *Guardrail:* If the Manim subprocess crashes (e.g., syntax error, invalid method), capture the `stderr`, feed it back to the LLM to fix the code (`gen_code_fix`), and retry (max 3 retries).
    *   *Failure State:* If it fails after max retries, mark the job as `FAILED` (Generation Error).

## 5. API Flow and Design

The API uses a standard asynchronous job pattern. Clients submit a request, receive a Job ID, poll for status, and finally retrieve the artifact.

The sum of all is 4 endpoints, each with their own unique flow and return types:

### 5.1. Submit Video Request (`POST /api/v1/videos`)
Initiates the asynchronous video generation process.
*   **Request Body (`application/json`)**:
    ```json
    {
      "prompt": "Why do atoms form covalent bonds?"
    }
    ```
*   **Success Response (`202 Accepted`)**:
    ```json
    {
      "job_id": "123e4567-e89b-12d3-a456-426614174000",
      "status": "WAITING",
      "message": "Video generation job submitted successfully."
    }
    ```
*   **Error Responses**:
    *   `400 Bad Request`: Invalid input format.
    *   `422 Unprocessable Entity`: Prompt fails basic validation (e.g., too short/long).

### 5.2. List All Jobs (`GET /api/v1/videos`)
Retrieves a list of all requested video jobs, sorted by creation date (descending).
*   **Success Response (`200 OK`)**:
    ```json
    [
      {
        "job_id": "123e4567-e89b-12d3-a456-426614174000",
        "prompt": "Why do atoms form covalent bonds?",
        "status": "COMPLETED",
        "created_at": "2023-10-27T10:00:00Z"
      }
    ]
    ```

### 5.3. Check Job Status (`GET /api/v1/videos/{job_id}`)
Used by the client to poll for updates on a specific job.
*   **Success Responses (`200 OK`)**:
    *   *If Processing:*
        ```json
        {
          "job_id": "123e4567-e89b-12d3-a456-426614174000",
          "status": "PROCESSING",
          "progress": "Generating Manim code...", 
          "created_at": "2023-10-27T10:00:00Z"
        }
        ```
    *   *If Failed:*
        ```json
        {
          "job_id": "123e4567-e89b-12d3-a456-426614174000",
          "status": "FAILED",
          "error_reason": "Prompt is not related to chemistry.",
          "created_at": "2023-10-27T10:00:00Z"
        }
        ```
*   **Error Responses**:
    *   `404 Not Found`: Job ID does not exist.

### 5.4. Retrieve Video Artifact (`GET /api/v1/videos/{job_id}/artifact`)
Streams or downloads the completed video file.
*   **Success Response (`200 OK`)**:
    *   Content-Type: `video/mp4`
    *   Content-Disposition: `attachment; filename="concept_video_123e4567...mp4"`
*   **Error Responses**:
    *   `404 Not Found`: Job ID does not exist, or file is missing from disk.
    *   `400 Bad Request`: Video is not ready (Status is WAITING, PROCESSING, or FAILED).

## 6. Database / State Management
For MVP, an in-memory dictionary or a simple SQLite database will be used to store job states:
*   `id`: UUID
*   `prompt`: String
*   `status`: Enum (WAITING, PROCESSING, COMPLETED, FAILED)
*   `video_path`: String (Nullable)
*   `error_reason`: String (Nullable)
*   `created_at`: Timestamp
*   `updated_at`: Timestamp

## 7. Reliability and Guardrails
*   **Non-determinism handling:** By splitting script generation from code generation, we limit the complexity the LLM has to handle at once.
*   **Feedback loop:** The automatic retry mechanism with error-traceback feedback to the LLM ensures that minor hallucinated Manim syntax errors don't cause a pipeline failure.
*   **Sandboxing:** Manim code is executed via `subprocess` with timeouts to prevent infinite loops from hanging the worker.
