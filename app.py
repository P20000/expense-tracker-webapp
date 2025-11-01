from flask import Flask, render_template, request, redirect, url_for, flash
import json, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = '970d6d1c8aa71b17c1a7806b084371f7ac6da281b4f5bd64e112f19d90d47399'  # change this for production

budget = {}
expenses = []

@app.route('/')
def home():
    return render_template('home.html', budget=budget, expenses=expenses)
@app.route('/set-budget', methods=['GET', 'POST'])
def set_budget():
    # Add form handling logic here later
    return render_template('set_budget.html')
@app.route('/add-expense', methods=['GET', 'POST'])
def add_expense():
    # You will add form handling here later
    return render_template('add_expense.html')
@app.route('/report')
def show_report():
    # Your logic to generate and show report goes here
    return render_template('report.html')


if __name__ == '__main__':
    app.run(debug=True)
