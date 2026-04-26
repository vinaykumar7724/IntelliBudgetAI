# IntelliBudget AI – Smart Finance & Expense Tracker Chatbot

This repository contains a full-stack deep learning powered finance and expense tracker chatbot built with Flask, TensorFlow/Keras, and MySQL.

## Features

- **User Authentication** with Flask-Login
- **Expense Tracking** (add, view, analyze)
- **Budget Management**
- **Dashboard** with charts (Chart.js)
- **AI Chatbot** for natural language expense management
- **Deep Learning Model** for intent classification (LSTM)
- **CSV Export** of expenses
- Responsive, modern UI using Bootstrap 5

## Setup Instructions

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd IntelliBudgetAI
   ```

2. **Create a virtual environment & install dependencies**
   ```bash
   python -m venv venv
   venv\Scripts\activate    # Windows
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   Create a `.env` file in the project root with the following:
   ```env
   SECRET_KEY=your-secret-key
   DATABASE_URL=mysql://user:password@localhost/intellibudget
   ```
   Adjust the database URI as needed. **Note:** if your password contains special characters such as `@`, `:` or `/`, either URL‑encode them (e.g. `@` → `%40`) or choose a simpler password; the config loader will attempt to quote the password automatically but malformed URLs can still cause connection failures.

4. **Initialize the database**
   Ensure MySQL server is running and a database named `intellibudget` exists.

5. **Train the chatbot model**
   ```bash
   python train_model.py
   ```
   This saves `model.h5`, `tokenizer.pkl`, and `label_encoder.pkl` to `models/`.

6. **Run the application**
   ```bash
   python app.py
   ```

7. **Access the app**
   Open `http://127.0.0.1:5000` in your browser

## Notes

- Passwords are hashed using Werkzeug.
- SQLAlchemy ORM is used to prevent injection.
- Environment variables handle sensitive configuration.

Enjoy tracking your finances with AI! 🎯
