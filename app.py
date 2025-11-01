from flask import Flask, render_template, request, redirect, url_for, flash
import json, os
from datetime import datetime
from flask import jsonify

app = Flask(__name__)
app.secret_key = '970d6d1c8aa71b17c1a7806b084371f7ac6da281b4f5bd64e112f19d90d47399'  # change this for production

budget = {}
expenses = []
category_file = "categories.json"
categories = [] # <<< CHANGE: Start with an empty list
# File names for persistence
expense_file = "expenditure.json"


def load_categories():
    global categories
    if os.path.exists(category_file):
        with open(category_file, 'r') as f:
            categories = json.load(f)
    else:
        save_categories()  # Save default on first run
def save_categories():
    with open(category_file, 'w') as f:
        json.dump(categories, f, indent=4)
def load_budget():
    global budget
    month = datetime.now().strftime("%Y-%m")
    budget_file = f"{month}.json"
    if os.path.exists(budget_file):
        with open(budget_file, 'r') as f:
            budget = json.load(f)
    else:
        budget = {}
def load_expenses():
    month = datetime.now().strftime("%Y-%m")
    if os.path.exists(expense_file):
        with open(expense_file, 'r') as f:
            all_expenses = json.load(f)
        expenses[:] = all_expenses.get(month, [])
    else:
        expenses.clear()
def save_budget_json():
    month = datetime.now().strftime("%Y-%m")
    budget_file = f"{month}.json"
    with open(budget_file, 'w') as f:
        json.dump(budget, f, indent=4)
def save_expenses_json():
    month = datetime.now().strftime("%Y-%m")
    all_expenses = {}
    if os.path.exists(expense_file):
        with open(expense_file, 'r') as f:
            all_expenses = json.load(f)
    # The 'expenses' here refers to the global list (READ operation)
    all_expenses.setdefault(month, []).extend(expenses) 
    with open(expense_file, 'w') as f:
        json.dump(all_expenses, f, indent=4)


# --- ROUTES --- #

@app.route('/')
def home():
    load_budget()
    load_expenses()
    print("debug expenses : ", expenses)
    return render_template('home.html', budget=budget, expenses=expenses)

@app.route('/set-budget', methods=['GET', 'POST'])
def set_budget():
    global categories  # Must be at very start before any use or assignment

    load_categories()
    load_budget()
    load_expenses()  # if needed

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_category_chips':
            categories_str = request.form.get('all_categories_hidden', '')
            new_cats = [c.strip() for c in categories_str.split(',') if c.strip()]
            # Remove duplicates preserving order
            new_unique = []
            for c in new_cats:
                if c not in new_unique:
                    new_unique.append(c)

            categories[:] = new_unique  # modify global list in place
            save_categories()
            flash("Categories updated.", "green")
            return redirect(url_for('set_budget'))

        # Other actions ...

    return render_template('set_budget.html', categories=categories, budget=budget)


@app.route('/add-expense', methods=['GET', 'POST'])

def add_expense():
    load_budget()
    if not budget:
        flash("Please set your budget before adding expenses.", "yellow")
        return redirect(url_for('set_budget'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_expense':
            # --- EXPENSE ADDITION LOGIC ---
            category = request.form.get('category')
            amount_raw = request.form.get('amount')
            
            if category not in categories:
                # If category is not in the list (user tampered or timing issue), reject
                flash(f"Unknown or invalid category selected.", "red lighten-2")
                return redirect(url_for('add_expense'))

            try:
                amount = float(amount_raw)
                if amount <= 0:
                    flash("Amount must be greater than zero.", "red lighten-2")
                    return redirect(url_for('add_expense'))
            except (ValueError, TypeError):
                flash("Invalid amount entered.", "red lighten-2")
                return redirect(url_for('add_expense'))

            date_str = datetime.now().strftime("%Y-%m-%d")
            global expenses
            expenses.append({"category": category, "amount": amount, "date": date_str})
            # NOTE: We are appending, not overwriting. This is important.
            save_expenses_json() 
            flash(f"➕ Expense added: {category} ₹{amount:.2f}", "green lighten-2")
            return redirect(url_for('home'))

        elif action == 'add_category':
            # --- CATEGORY ADDITION LOGIC ---
            new_cat = request.form.get('new_category', '').strip()
            if not new_cat:
                flash("Category name cannot be empty.", "red lighten-2")
            elif new_cat in categories:
                flash("Category already exists.", "yellow lighten-2")
            else:
                categories.append(new_cat)
                save_categories()
                flash(f"Category '{new_cat}' added successfully!", "green lighten-2")
            return redirect(url_for('add_expense'))

        elif action == 'delete_category':
            # --- CATEGORY DELETION LOGIC ---
            cat_to_delete = request.form.get('delete_cat')
            if cat_to_delete and cat_to_delete in categories:
                categories.remove(cat_to_delete)
                save_categories()

                # Remove related expenses globally
                # global expenses
                expenses = [e for e in expenses if e['category'] != cat_to_delete]
                save_expenses_json()
                
                flash(f"Category '{cat_to_delete}' deleted along with related expenses.", 'red darken-2')
            else:
                flash("Invalid category selected for deletion.", 'yellow darken-2')
            return redirect(url_for('add_expense'))

    # Handle GET request (rendering the form)
    # Pass all categories for the dropdown and the management section
    return render_template('add_expense.html', categories=categories)

@app.route('/report')
def show_report():
    load_budget()
    load_expenses()
    return render_template('report.html', budget=budget, expenses=expenses)

@app.route('/add-category', methods=['GET', 'POST'])
def add_category():
    load_categories()
    if request.method == 'POST':
        new_cat = request.form.get('new_category', '').strip()
        if not new_cat:
            flash("Category name cannot be empty.", "red lighten-2")
        elif new_cat in categories:
            flash("Category already exists.", "yellow lighten-2")
        else:
            categories.append(new_cat)
            save_categories()
            flash(f"Category '{new_cat}' added successfully!", "green lighten-2")
            return redirect(url_for('add_expense'))
    return render_template('add_category.html', categories=categories)

@app.route('/manage-categories', methods=['GET', 'POST'])
def manage_categories():
    load_categories()
    load_expenses()
    if request.method == 'POST':
        # Handle deletions from submitted category list
        to_delete = request.form.getlist('delete_categories')
        if to_delete:
            # Confirm categories exist
            for cat in to_delete:
                if cat in categories:
                    categories.remove(cat)
            save_categories()

            # Remove related expenses
            global expenses
            expenses = [e for e in expenses if e['category'] not in to_delete]

            # Save expenses again after removals
            save_expenses_json()

            flash(f"Deleted categories: {', '.join(to_delete)} and related expenses.", 'green lighten-2')
            return redirect(url_for('manage_categories'))

    # On GET, render management page
    return render_template('manage_categories.html', categories=categories)


if __name__ == '__main__':
    app.run(debug=True)
