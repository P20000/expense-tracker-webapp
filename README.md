# Expense Tracker Web Application

## Overview
This is a Flask-based web application for tracking monthly budgets and expenses. The app allows users to set budgets in categories like Food, Travel, and Entertainment, add daily expenses against these categories, and view detailed reports comparing spending versus budget limits.

Built with Python and Flask, this project serves as both a practical personal finance tool and a college-level assignment demonstrating web development, data persistence, and user interaction.
link: https://expense-tracker-webapp-one.vercel.app/
<img width="1062" height="635" alt="image" src="https://github.com/user-attachments/assets/bab0fb55-5b91-4190-a698-161e657a5560" />

---

## Features
- Set monthly budgets for multiple categories.
- Add expenses with category and amount.
- Dynamic report showing spending vs. budget status.
- Persistent data storage using JSON files.
- Simple and clean web interface with Flask templating.

---

## Technologies Used
- Python 3
- Flask Web Framework
- HTML/Jinja2 for templates
- CSS (optional for styling)
- JSON for data storage

---

## Installation

1. Clone the repository:

```
git clone https://github.com/P20000/expense-tracker-webapp.git
cd expense-tracker-webapp
```

2. (Optional but recommended) Create and activate a Python virtual environment:

```
python -m venv venv
source venv/bin/activate      # On Windows use: venv\Scripts\activate
```

3. Install dependencies:

```
pip install flask
```

---

## Usage

1. Run the Flask app:

```
python app.py
```

2. Open your browser and navigate to:

```
http://127.0.0.1:5000/
```

3. Use the navigation links to:
   - Set your monthly budget.
   - Add your daily expenses.
   - View the expense report.

---

## File Structure

```
expense-tracker-webapp/
├── app.py              # Main Flask application file
├── templates/          # HTML templates used by Flask
│   ├── home.html
│   ├── set_budget.html
│   ├── add_expense.html
│   └── report.html
├── static/             # Static files, e.g. CSS (optional)
│   └── style.css
├── expenditure.json    # JSON file storing all expense records
└── README.md           # Project README (this file)
```

---

## Data Persistence

- Budgets and expenses are saved in JSON files to maintain state between sessions.
- Monthly budgets are saved as `<YYYY-MM>.json`.
- All expenses are stored collectively in `expenditure.json` organized by month.

---

## Deployment

To deploy this app live:

- Choose a hosting provider that supports Python and Flask (e.g., Render, Heroku, DigitalOcean).
- Push your code to GitHub.
- Follow provider’s instructions to deploy a Flask app from the GitHub repository.
- Set environment variables securely, especially `SECRET_KEY` for Flask.
 
---

## Security

- The Flask app uses a `SECRET_KEY` for session security. Generate a secure key using Python’s `secrets` module.
- Do not expose your secret key publicly or commit it to your repository.
- Use environment variables or external config files to store sensitive data in production.

---

## Contributing

Contributions and suggestions are welcome!  
To contribute:

1. Fork the repository.
2. Create your feature branch (`git checkout -b feature-name`).
3. Commit your changes (`git commit -m 'Add some feature'`).
4. Push to the branch (`git push origin feature-name`).
5. Open a Pull Request.

---

## License

This project is open source under the MIT License.

---

## Contact

For questions or suggestions, please contact [Your Name or Email].

---

*Thank you for checking out this project!*
EOF
