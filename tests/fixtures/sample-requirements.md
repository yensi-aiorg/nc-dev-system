# Task Management App

## Overview
A web application for managing personal and team tasks with priorities, categories, and due dates. Users can create, organize, and track their tasks through an intuitive dashboard.

## Features

### User Authentication (P0)
- Email/password registration with validation
- Email/password login
- Session management with JWT tokens
- Password reset via email link
- Logout functionality

**Routes:**
- /login - Login page
- /register - Registration page
- /forgot-password - Password reset request

**API Endpoints:**
- POST /api/v1/auth/register - Create new account
- POST /api/v1/auth/login - Authenticate user
- POST /api/v1/auth/logout - End session
- POST /api/v1/auth/forgot-password - Request password reset
- POST /api/v1/auth/reset-password - Reset password with token

### Task CRUD (P0)
- Create tasks with title, description, priority (low/medium/high/urgent), due date
- View task list with pagination
- View single task details
- Update task properties (title, description, priority, due date, status)
- Delete tasks (soft delete - mark as deleted, don't remove from DB)
- Task status workflow: todo → in_progress → done

**Routes:**
- /tasks - Task list page
- /tasks/new - Create task form
- /tasks/:id - Task detail/edit page

**API Endpoints:**
- GET /api/v1/tasks - List tasks (paginated, filterable)
- POST /api/v1/tasks - Create task
- GET /api/v1/tasks/:id - Get task details
- PUT /api/v1/tasks/:id - Update task
- DELETE /api/v1/tasks/:id - Soft delete task

### Task Categories (P1)
- Create and manage categories (name, color, icon)
- Assign categories to tasks (many-to-many)
- Filter tasks by category
- Category management page

**Routes:**
- /categories - Category management page

**API Endpoints:**
- GET /api/v1/categories - List categories
- POST /api/v1/categories - Create category
- PUT /api/v1/categories/:id - Update category
- DELETE /api/v1/categories/:id - Delete category

### Dashboard (P1)
- Task statistics overview (total, completed, overdue, by priority)
- Tasks due today/this week widget
- Recent activity feed
- Category distribution chart

**Routes:**
- / - Dashboard (home page)

**API Endpoints:**
- GET /api/v1/dashboard/stats - Get task statistics
- GET /api/v1/dashboard/recent - Get recent activity

### Search & Filter (P1)
- Full-text search across task titles and descriptions
- Filter by status (todo, in_progress, done)
- Filter by priority (low, medium, high, urgent)
- Filter by category
- Filter by due date range
- Sort by created date, due date, priority

**API Endpoints:**
- GET /api/v1/tasks/search?q=... - Search tasks
(Uses the existing GET /api/v1/tasks with query parameters)

### Responsive Design (P2)
- Mobile-first responsive layout
- Touch-friendly task interactions
- Collapsible sidebar on mobile
- Bottom navigation on mobile

## Database Schema

### Users Collection
- _id: ObjectId
- email: string (unique, indexed)
- password_hash: string
- name: string
- created_at: datetime
- updated_at: datetime

### Tasks Collection
- _id: ObjectId
- title: string (indexed)
- description: string
- status: string (enum: todo, in_progress, done)
- priority: string (enum: low, medium, high, urgent)
- due_date: datetime (indexed)
- category_ids: ObjectId[] (ref: categories)
- user_id: ObjectId (ref: users, indexed)
- is_deleted: boolean (default: false)
- created_at: datetime
- updated_at: datetime

### Categories Collection
- _id: ObjectId
- name: string
- color: string (hex)
- icon: string
- user_id: ObjectId (ref: users, indexed)
- created_at: datetime
- updated_at: datetime

## External APIs
None - this is a self-contained application.

## Non-Functional Requirements
- Response time: < 200ms for API calls
- Support 100 concurrent users
- Mobile responsive (320px - 2560px)
- WCAG AA accessibility compliance
- Secure password storage (bcrypt)
