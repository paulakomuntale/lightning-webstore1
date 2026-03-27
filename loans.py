import time
from datetime import datetime, timedelta
from database import Database

class LoanManager:
    def __init__(self, db, config):
        self.db = db
        self.config = config
    
    def calculate_total_payable(self, amount, days):
        """Calculate total amount to repay with interest"""
        interest = amount * self.config['interest_rate'] / 100
        return amount + interest
    
    def create_loan_request(self, borrower_id, borrower_name, amount, days, purpose):
        """Create a new loan request"""
        # Validate
        if amount < self.config['min_loan']:
            return None, f"Minimum loan is {self.config['min_loan']} sats"
        if amount > self.config['max_loan']:
            return None, f"Maximum loan is {self.config['max_loan']} sats"
        if days < self.config['min_days']:
            return None, f"Minimum loan period is {self.config['min_days']} days"
        if days > self.config['max_days']:
            return None, f"Maximum loan period is {self.config['max_days']} days"
        
        # Calculate repayment amounts
        total_payable = self.calculate_total_payable(amount, days)
        interest_amount = total_payable - amount
        
        # Create loan record
        loan_data = {
            'borrower_id': borrower_id,
            'borrower_name': borrower_name,
            'amount_sats': amount,
            'interest_sats': interest_amount,
            'total_payable_sats': total_payable,
            'days': days,
            'purpose': purpose,
            'due_date': int(time.time()) + (days * 24 * 3600),
            'status': 'pending'
        }
        
        loan = self.db.create_loan(loan_data)
        return loan, "Loan request created successfully"
    
    def fund_loan(self, loan_id, lender_id, lender_name, funding_tx):
        """Fund a loan request"""
        loan = self.db.get_loan(loan_id)
        if not loan or loan['status'] != 'pending':
            return None, "Loan not available"
        
        # Update loan with funding info
        updates = {
            'lender_id': lender_id,
            'lender_name': lender_name,
            'funding_tx': funding_tx,
            'funded_at': int(time.time()),
            'status': 'funded'
        }
        
        loan = self.db.update_loan(loan_id, updates)
        
        # Update borrower stats
        borrower = self.db.get_user(loan['borrower_id'])
        if borrower:
            self.db.update_user(borrower['id'], {
                'total_borrowed': borrower.get('total_borrowed', 0) + loan['amount_sats'],
                'active_loans': borrower.get('active_loans', 0) + 1
            })
        
        return loan, "Loan funded successfully"
    
    def make_repayment(self, loan_id, amount_sats, transaction_hash):
        """Make a repayment towards a loan"""
        loan = self.db.get_loan(loan_id)
        if not loan or loan['status'] not in ['funded', 'active']:
            return None, "Loan not active"
        
        # Record repayment
        repayment = self.db.add_repayment(loan_id, amount_sats, transaction_hash)
        
        # Check if loan is fully repaid
        total_repaid = self.db.get_total_repaid(loan_id)
        
        if total_repaid >= loan['total_payable_sats']:
            # Loan fully repaid
            updates = {
                'status': 'repaid',
                'repaid_at': int(time.time()),
                'total_repaid': total_repaid
            }
            self.db.update_loan(loan_id, updates)
            
            # Update user stats
            borrower = self.db.get_user(loan['borrower_id'])
            if borrower:
                self.db.update_user(borrower['id'], {
                    'total_repaid': borrower.get('total_repaid', 0) + loan['total_payable_sats'],
                    'active_loans': borrower.get('active_loans', 0) - 1,
                    'completed_loans': borrower.get('completed_loans', 0) + 1,
                    'reputation': min(100, borrower.get('reputation', 100) + 5)  # Increase reputation
                })
            
            # Update lender stats
            lender = self.db.get_user(loan['lender_id'])
            if lender:
                self.db.update_user(lender['id'], {
                    'total_earned': lender.get('total_earned', 0) + loan['interest_sats']
                })
            
            return repayment, "Loan fully repaid! 🎉"
        else:
            # Partial payment
            loan = self.db.update_loan(loan_id, {'total_repaid': total_repaid})
            return repayment, f"Payment received. Remaining: {loan['total_payable_sats'] - total_repaid} sats"
    
    def check_overdue_loans(self):
        """Check and update overdue loans"""
        now = int(time.time())
        active_loans = self.db.get_active_loans()
        
        for loan in active_loans:
            if loan['due_date'] < now:
                # Loan is overdue
                days_overdue = (now - loan['due_date']) // (24 * 3600)
                late_fee = loan['amount_sats'] * self.config['late_fee'] / 100
                new_total = loan['total_payable_sats'] + late_fee
                
                self.db.update_loan(loan['id'], {
                    'status': 'overdue',
                    'days_overdue': days_overdue,
                    'late_fee': late_fee,
                    'total_payable_sats': new_total
                })
                
                # Reduce borrower reputation
                borrower = self.db.get_user(loan['borrower_id'])
                if borrower:
                    new_reputation = max(0, borrower.get('reputation', 100) - 10)
                    self.db.update_user(borrower['id'], {'reputation': new_reputation})
    
    def get_loan_summary(self):
        """Get summary of all loans"""
        all_loans = self.db._load_json(self.db.loans_file)
        
        return {
            'total_loans': len(all_loans),
            'total_amount': sum(l['amount_sats'] for l in all_loans),
            'total_interest': sum(l.get('interest_sats', 0) for l in all_loans),
            'pending': len([l for l in all_loans if l['status'] == 'pending']),
            'active': len([l for l in all_loans if l['status'] in ['funded', 'active']]),
            'repaid': len([l for l in all_loans if l['status'] == 'repaid']),
            'overdue': len([l for l in all_loans if l['status'] == 'overdue'])
        }
    




