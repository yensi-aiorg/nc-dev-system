# Task Management App

A web application for managing tasks and projects with team collaboration.

## Features

### User Authentication (P0)
- Email/password login and registration
- Session management
- Password reset flow
- Depends on "User Authentication" for session handling

### Task CRUD (P0)
- Create tasks with title, description, priority, due date
- Read/list tasks with pagination
- Update task details
- Delete tasks (soft delete)
- Filter tasks by status and priority

### Project Management (P1)
- Create and manage projects
- Assign tasks to projects
- View project dashboard with task statistics
- Requires "Task CRUD" for task assignment

### Team Collaboration (P2)
- Invite team members via email
- Real-time notifications via websocket
- Comment on tasks
- Integration with Slack for notifications

### Reporting Dashboard (P1)
- View task completion statistics
- Generate PDF reports (TBD on exact format)
- Export data to CSV
- Analytics might need some kind of third-party tool

## UI/Routes

- `/dashboard` - Main dashboard with overview
- `/tasks` - Task list with filters
- `/tasks/:id` - Task detail view
- `/projects` - Project list
- `/settings` - User settings

## Authentication

All routes except login and register require authentication.
KeyCloak will be used for SSO.
