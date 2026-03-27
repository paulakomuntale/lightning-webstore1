from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import json
import time
from datetime import datetime

from config import LND_CONFIG, LOAN_CONFIG, APP_CONFIG
from database import Database
from loans import LoanManager
from payments import PaymentManager

app = Flask(__name__)
app.secret_key = 'lightning-lend-secret-key-change-in-production'

# Initialize modules
db = Database()
loan_manager = LoanManager(db, LOAN_CONFIG)
payment_manager = PaymentManager(LND_CONFIG)

# Helper functions
def get_user_from_session():
    user_id = session.get('user_id')
    if user_id:
        return db.get_user(user_id)
    return None

@app.route('/')
def index():
    user = get_user_from_session()
    if not user:
        return redirect(url_for('register'))
    
    # Get user's loans
    my_loans = db.get_loans_by_user(user['id'], 'borrower')
    active_loans = [l for l in my_loans if l['status'] in ['funded', 'active']]
    completed_loans = [l for l in my_loans if l['status'] == 'repaid']
    
    # Get risk profile (this IS your collateral based on reputation)
    risk_profile = db.get_user_risk_profile(user['id'])
    
    # Get platform summary stats
    summary = loan_manager.get_loan_summary()  # ← ADD THIS LINE
    
    return render_template('index.html', 
                         user=user,
                         active_loans=active_loans,
                         completed_loans=completed_loans,
                         risk_profile=risk_profile,
                         summary=summary)  # ← ADD THIS

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        user_id = email
        
        user = db.create_user(user_id, name, email)
        session['user_id'] = user_id
        session['user_name'] = name
        
        return redirect(url_for('index'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('register'))

@app.route('/request_loan', methods=['GET', 'POST'])
def request_loan():
    user = get_user_from_session()
    if not user:
        return redirect(url_for('register'))
    
    # Get user's risk profile (this acts as their collateral)
    try:
        risk_profile = db.get_user_risk_profile(user['id'])
        print(f"DEBUG - Risk profile: {risk_profile}")
    except Exception as e:
        print(f"Error getting risk profile: {e}")
        risk_profile = {
            'risk_level': 'new',
            'risk_score': 100,
            'recommended_max_loan': 50000,
            'interest_rate': 5,
            'description': 'First-time borrower - Building trust',
            'total_loans_completed': 0,
            'on_time_percentage': 100,
            'collateral_type': 'Trust-based'
        }
    
    max_loan = risk_profile.get('recommended_max_loan', 50000)
    interest_rate = risk_profile.get('interest_rate', 5)
    
    # Collateral is based on REPUTATION, not funds
    is_first_loan = risk_profile.get('total_loans_completed', 0) == 0
    collateral_message = "✨ First-time borrower! No collateral needed. Your trust is being built."
    
    if not is_first_loan:
        collateral_message = f"🏆 Based on your {risk_profile['risk_level'].upper()} reputation ({risk_profile['risk_score']}/100), you qualify for a loan up to {max_loan:,} sats at {interest_rate}% interest. Your repayment history is your collateral!"
    
    if request.method == 'POST':
        amount = int(request.form['amount'])
        days = int(request.form['days'])
        purpose = request.form['purpose']
        
        # Validation
        if amount > max_loan:
            return render_template('request_loan.html', 
                                 error=f"Your maximum loan is {max_loan:,} sats",
                                 config=LOAN_CONFIG,
                                 risk_profile=risk_profile,
                                 max_loan=max_loan,
                                 interest_rate=interest_rate,
                                 is_first_loan=is_first_loan,
                                 collateral_message=collateral_message)
        
        if amount < LOAN_CONFIG['min_loan']:
            return render_template('request_loan.html', 
                                 error=f"Minimum loan is {LOAN_CONFIG['min_loan']:,} sats",
                                 config=LOAN_CONFIG,
                                 risk_profile=risk_profile,
                                 max_loan=max_loan,
                                 interest_rate=interest_rate,
                                 is_first_loan=is_first_loan,
                                 collateral_message=collateral_message)
        
        # Create loan request (with reputation as collateral)
        loan, message = loan_manager.create_loan_request(
            borrower_id=user['id'],
            borrower_name=user['name'],
            amount=amount,
            days=days,
            purpose=purpose
        )
        
        if loan:
            # Store loan in session for funding
            session['pending_loan'] = loan['id']
            return redirect(url_for('fund_loan', loan_id=loan['id']))
        else:
            return render_template('request_loan.html', 
                                 error=message,
                                 config=LOAN_CONFIG,
                                 risk_profile=risk_profile,
                                 max_loan=max_loan,
                                 interest_rate=interest_rate,
                                 is_first_loan=is_first_loan,
                                 collateral_message=collateral_message)
    
    return render_template('request_loan.html', 
                         config=LOAN_CONFIG,
                         risk_profile=risk_profile,
                         max_loan=max_loan,
                         interest_rate=interest_rate,
                         is_first_loan=is_first_loan,
                         collateral_message=collateral_message)

@app.route('/fund_loan/<int:loan_id>')
def fund_loan(loan_id):
    """Generate invoice to receive the loan amount"""
    user = get_user_from_session()
    if not user:
        return redirect(url_for('register'))
    
    loan = db.get_loan(loan_id)
    if not loan or loan['borrower_id'] != user['id']:
        return "Loan not found", 404
    
    if loan['status'] != 'pending':
        return redirect(url_for('loan_detail', loan_id=loan_id))
    
    # Generate invoice for the loan amount
    invoice = payment_manager.generate_invoice(
        amount_sats=loan['amount_sats'],
        memo=f"Loan #{loan_id} - {loan['amount_sats']} sats"
    )
    
    if invoice:
        return render_template('receive_funds.html', 
                             invoice=invoice,
                             loan=loan,
                             amount=loan['amount_sats'])
    
    return "Error generating invoice", 500

@app.route('/confirm_funding', methods=['POST'])
def confirm_funding():
    """Confirm that the loan has been funded"""
    user = get_user_from_session()
    if not user:
        return redirect(url_for('register'))
    
    r_hash = request.form.get('r_hash')
    loan_id = request.form.get('loan_id')
    
    # Check if payment was made
    if payment_manager.check_payment(r_hash):
        # Update loan to funded status
        loan = db.update_loan(int(loan_id), {
            'status': 'funded',
            'funded_at': int(time.time()),
            'funding_tx': r_hash
        })
        
        # Update user stats
        user_data = db.get_user(user['id'])
        db.update_user(user['id'], {
            'total_borrowed': user_data.get('total_borrowed', 0) + loan['amount_sats'],
            'active_loans': user_data.get('active_loans', 0) + 1
        })
        
        return redirect(url_for('loan_detail', loan_id=loan_id))
    else:
        return "Payment not confirmed. Please try again.", 400

@app.route('/loan/<int:loan_id>')
def loan_detail(loan_id):
    user = get_user_from_session()
    if not user:
        return redirect(url_for('register'))
    
    loan = db.get_loan(loan_id)
    if not loan or loan['borrower_id'] != user['id']:
        return "Loan not found", 404
    
    repayments = db.get_repayments(loan_id)
    total_repaid = db.get_total_repaid(loan_id)
    remaining = loan['total_payable_sats'] - total_repaid
    
    # Get updated risk profile to show reputation impact
    risk_profile = db.get_user_risk_profile(user['id'])
    
    return render_template('loan_detail.html', 
                         loan=loan, 
                         repayments=repayments,
                         total_repaid=total_repaid,
                         remaining=remaining,
                         user=user,
                         risk_profile=risk_profile)

@app.route('/repay/<int:loan_id>', methods=['GET', 'POST'])
def repay(loan_id):
    """Generate invoice to repay the loan"""
    user = get_user_from_session()
    if not user:
        return redirect(url_for('register'))
    
    loan = db.get_loan(loan_id)
    if not loan or loan['borrower_id'] != user['id']:
        return "Not authorized", 403
    
    if loan['status'] not in ['funded', 'active', 'overdue']:
        return "Loan cannot be repaid", 400
    
    total_repaid = db.get_total_repaid(loan_id)
    remaining = loan['total_payable_sats'] - total_repaid
    
    if request.method == 'POST':
        amount = int(request.form['amount'])
        
        if amount > remaining:
            return render_template('repay.html', 
                                 error=f"Amount exceeds remaining balance of {remaining} sats",
                                 loan=loan, 
                                 remaining=remaining,
                                 total_repaid=total_repaid)
        
        # Generate invoice for repayment
        invoice = payment_manager.generate_invoice(
            amount_sats=amount,
            memo=f"Repayment for Loan #{loan_id}"
        )
        
        if invoice:
            session['repay_loan'] = loan_id
            session['repay_amount'] = amount
            return render_template('pay_repayment.html', 
                                 invoice=invoice,
                                 loan=loan,
                                 amount=amount,
                                 remaining=remaining)
    
    return render_template('repay.html', 
                         loan=loan, 
                         remaining=remaining,
                         total_repaid=total_repaid)

@app.route('/confirm_repayment', methods=['POST'])
def confirm_repayment():
    """Confirm repayment payment"""
    user = get_user_from_session()
    if not user:
        return redirect(url_for('register'))
    
    r_hash = request.form.get('r_hash')
    loan_id = session.get('repay_loan')
    amount = session.get('repay_amount')
    
    if not loan_id:
        return "No repayment pending", 400
    
    # Check if payment was made
    if payment_manager.check_payment(r_hash):
        # Record repayment
        result, message = loan_manager.make_repayment(loan_id, amount, r_hash)
        
        session.pop('repay_loan', None)
        session.pop('repay_amount', None)
        
        return redirect(url_for('loan_detail', loan_id=loan_id))
    else:
        return "Payment not confirmed. Please try again.", 400

@app.route('/my_loans')
def my_loans():
    user = get_user_from_session()
    if not user:
        return redirect(url_for('register'))
    
    loans = db.get_loans_by_user(user['id'], 'borrower')
    
    return render_template('my_loans.html', 
                         loans=loans,
                         config=LOAN_CONFIG)

@app.route('/dashboard')
def dashboard():
    user = get_user_from_session()
    if not user:
        return redirect(url_for('register'))
    
    loans = db.get_loans_by_user(user['id'], 'borrower')
    risk_profile = db.get_user_risk_profile(user['id'])
    
    return render_template('dashboard.html', 
                         user=user, 
                         loans=loans,
                         risk_profile=risk_profile)

@app.route('/api/check_payment/<r_hash>')
def check_payment(r_hash):
    """API endpoint to check payment status"""
    try:
        settled = payment_manager.check_payment(r_hash)
        return jsonify({"settled": settled})
    except Exception as e:
        return jsonify({"settled": False, "error": str(e)})

if __name__ == '__main__':
    print("=" * 60)
    print("  LIGHTNING BORROW PLATFORM")
    print("=" * 60)
    print("COLLATERAL SYSTEM: Reputation-Based")
    print("  - First loan: No collateral needed")
    print("  - Subsequent loans: Your repayment history = collateral")
    print("  - Good behavior = Better rates & higher limits")
    print()
    print(f"Min Loan: {LOAN_CONFIG['min_loan']} sats")
    print(f"Max Loan: {LOAN_CONFIG['max_loan']} sats")
    print(f"Interest Rate: {LOAN_CONFIG['interest_rate']}%")
    print(f"Loan Period: {LOAN_CONFIG['min_days']}-{LOAN_CONFIG['max_days']} days")
    print()
    print(f"Running at: http://{APP_CONFIG['host']}:{APP_CONFIG['port']}")
    print("Press Ctrl+C to stop")
    print()
    
    app.run(debug=APP_CONFIG['debug'],
            host=APP_CONFIG['host'],
            port=APP_CONFIG['port'])