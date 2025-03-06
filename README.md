# Simple ERP/MRP for Sheet Metal Management

This repository contains a simple ERP/MRP web application built with Flask and SQLAlchemy to help manage sheet metal (blachy) orders and projects. The application offers the following features:

## Features

### CRUD for Sheet Metal
- **Create, Read, Update, and Delete** sheet metal records.
- Display key information including:
  - Code
  - Simple name
  - Material
  - Thickness
  - Current stock
  - Required stock (dynamically calculated from project requirements)

### File Uploads
- Upload related files (PDF, DXF) for each sheet metal record.
- View uploaded files via provided links.

### Offer Generation
- Generate a text file offer for sheet metal shortages.
- Option to override the calculated shortage using checkboxes (display "X szt." instead of a number).

### Projects Module
- Create and manage projects.
- Assign sheet metal records to projects with specific required quantities.
- The required stock for each sheet metal record is dynamically calculated as the sum of all project requirements.

### Materials & Thickness Management
- Manage available material options and thickness values through dedicated pages.
- Use drop-down menus in sheet metal forms to select material and thickness from available options.
- Easily add new materials or thickness options.

### Dockerized Deployment with Persistent Storage
- The application is containerized using Docker and Docker Compose.
- The SQLite database file (`blachy.db`) and uploaded files are stored in persistent volumes outside of the application directory, ensuring data persistence between container restarts.
