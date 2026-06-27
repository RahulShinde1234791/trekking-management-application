# Trekking Management Application

A Flask-based web application for managing trekking activities involving Admins, Trek Staff, and Trekkers. This is a MAD1 project for managing trekking activities using Python.

The system will support trek creation, staff approval, bookings, role-based dashboards, and trekking history tracking.

## Tech Stack

- Flask
- Jinja2
- HTML
- CSS
- Bootstrap
- SQLite

## Project Status

Milestone 0: GitHub repository setup and initial project files.

Milestone 1: Database models and schema setup complete.

Milestone 2: Authentication and role-based access complete.

Milestone 3: Admin dashboard and management complete.

## Database Setup

Run this command to create the SQLite database and pre-create the admin user:

```bash
python init_db.py
```

Default development admin:

- Email: `admin@trekking.local`
- Password: `admin123`

## Current Features

- Trekker registration and login
- Trek staff registration with admin approval before login
- Predefined admin login
- Role-specific dashboards for Admin, Trek Staff, and Trekker
- Admin counts for treks, users, staff, and bookings
- Admin trek create, edit, remove, assign staff, and search
- Admin staff approve, add, blacklist, activate, remove, and search
- Admin user blacklist, activate, and search
- Admin booking and trekking history view
