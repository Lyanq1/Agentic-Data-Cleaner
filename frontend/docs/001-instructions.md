You are a senior Frontend Engineer working on a Graduation Thesis project.

## Objective
Your task is to analyze the entire existing codebase and design + implement a frontend system that integrates tightly with the current backend APIs.

## Step 1: Codebase Understanding
- Scan and understand the full project structure (Frontend and backend)
- Identify:
  - Existing routing structure (if any)
  - API endpoints (GET, POST, PUT, DELETE)
  - Data models / response formats
- Summarize your understanding before implementing anything

## Step 2: Frontend Architecture Design
- Use: React, TailwindCSS, ShadCN UI
- Design a clean and minimal structure: 
  - pages / app router
  - components (reusable, atomic) 
  - services/api layer (fetch/axios abstraction)
  - state management (simple: useState/useQuery, avoid overengineering)

## Step 3: UI/UX Requirements
- Prioritize:
  - Fast loading
  - Minimalist UI
  - Easy-to-use forms
- All API interactions (GET/POST) must:
  - Be clearly represented in UI
  - Have simple forms (input, textarea, select)
  - Show loading / success / error states
  - Show breadcrumb for each step (for pipelines)

## Step 4: Implementation Rules
- Do NOT overcomplicate (this is a thesis project, not production-scale SaaS)
- Avoid unnecessary libraries
- Code must be:
  - Clean
  - Readable
  - Easy to explain during thesis defense

## Step 5: Output Format
You MUST:
1. Explain the proposed frontend structure
2. Map each UI screen to backend API
3. Generate actual code for:
   - Layout
   - API calling layer
   - At least 2–3 main screens (CRUD or core feature)
4. Clearly explain how data flows from UI → API → UI

## Step 6: Optimization Thinking
- Suggest improvements for:
  - Performance (lazy load, caching)
  - UX (form validation, feedback)
  - Scalability (if extended later)
  - Clean code practices
  - Software architecture thinking

## Constraints
- Keep UI lightweight and fast
- Focus on usability over visual complexity
- Ensure everything works with current backend APIs (DO NOT assume new APIs)