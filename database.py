import json
import os
from datetime import datetime
import time

from config import LOAN_CONFIG

class Database:
    def __init__(self):
        self.data_dir = 'data'
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.loans_file = f'{self.data_dir}/loans.json'
        self.users_file = f'{self.data_dir}/users.json'
        self.repayments_file = f'{self.data_dir}/repayments.json'
        
        self._init_files()
    
    def _init_files(self):
        """Initialize database files if they don't exist"""
        if not os.path.exists(self.loans_file):
            self._save_json(self.loans_file, [])
        if not os.path.exists(self.users_file):
            self._save_json(self.users_file, {})
        if not os.path.exists(self.repayments_file):
            self._save_json(self.repayments_file, [])
    
    def _load_json(self, filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except:
            return [] if 'loans' in filepath else {}
    
    def _save_json(self, filepath, data):
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    # User methods
    def get_user(self, user_id):
        users = self._load_json(self.users_file)
        return users.get(user_id)
    
    def create_user(self, user_id, name, email):
        users = self._load_json(self.users_file)
        if user_id not in users:
            users[user_id] = {
                'id': user_id,
                'name': name,
                'email': email,
                'created_at': int(time.time()),
                'total_borrowed': 0,
                'total_repaid': 0,
                'active_loans': 0,
                'completed_loans': 0,
                'reputation': 100
            }
            self._save_json(self.users_file, users)
        return users[user_id]
    
    def update_user(self, user_id, updates):
        users = self._load_json(self.users_file)
        if user_id in users:
            users[user_id].update(updates)
            self._save_json(self.users_file, users)
            return users[user_id]
        return None
    
    # Loan methods
    def create_loan(self, loan_data):
        loans = self._load_json(self.loans_file)
        loan_id = len(loans) + 1
        loan = {
            'id': loan_id,
            'created_at': int(time.time()),
            'status': 'pending',
            **loan_data
        }
        loans.append(loan)
        self._save_json(self.loans_file, loans)
        return loan
    
    def get_loan(self, loan_id):
        loans = self._load_json(self.loans_file)
        for loan in loans:
            if loan['id'] == loan_id:
                return loan
        return None
    
    def update_loan(self, loan_id, updates):
        loans = self._load_json(self.loans_file)
        for loan in loans:
            if loan['id'] == loan_id:
                loan.update(updates)
                self._save_json(self.loans_file, loans)
                return loan
        return None
    
    def get_loans_by_user(self, user_id, role='borrower'):
        loans = self._load_json(self.loans_file)
        if role == 'borrower':
            return [l for l in loans if l.get('borrower_id') == user_id]
        else:
            return [l for l in loans if l.get('lender_id') == user_id]
    
    def get_active_loans(self):
        loans = self._load_json(self.loans_file)
        return [l for l in loans if l.get('status') in ['funded', 'active']]
    
    def get_pending_loans(self):
        loans = self._load_json(self.loans_file)
        return [l for l in loans if l.get('status') == 'pending']
    
    # Repayment methods
    def add_repayment(self, loan_id, amount_sats, transaction_hash):
        repayments = self._load_json(self.repayments_file)
        repayment = {
            'loan_id': loan_id,
            'amount_sats': amount_sats,
            'transaction_hash': transaction_hash,
            'timestamp': int(time.time()),
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        repayments.append(repayment)
        self._save_json(self.repayments_file, repayments)
        return repayment
    
    def get_repayments(self, loan_id):
        repayments = self._load_json(self.repayments_file)
        return [r for r in repayments if r['loan_id'] == loan_id]
    
    def get_total_repaid(self, loan_id):
        repayments = self.get_repayments(loan_id)
        return sum(r['amount_sats'] for r in repayments)
    
    def get_user_loan_history(self, user_id):
        """Get complete loan history for a user"""
        loans = self._load_json(self.loans_file)
        user_loans = [l for l in loans if l.get('borrower_id') == user_id]
        
        history = {
            'total_loans': len(user_loans),
            'completed_loans': len([l for l in user_loans if l['status'] == 'repaid']),
            'active_loans': len([l for l in user_loans if l['status'] in ['funded', 'active']]),
            'overdue_loans': len([l for l in user_loans if l['status'] == 'overdue']),
            'defaulted_loans': len([l for l in user_loans if l['status'] == 'defaulted']),
            'total_borrowed': sum(l['amount_sats'] for l in user_loans),
            'total_repaid': sum(l.get('total_repaid', 0) for l in user_loans),
            'on_time_payments': 0,
            'late_payments': 0
        }
        
        # Calculate payment behavior
        for loan in user_loans:
            if loan.get('status') == 'repaid':
                due_date = loan.get('due_date', 0)
                repaid_at = loan.get('repaid_at', 0)
                if repaid_at and repaid_at <= due_date:
                    history['on_time_payments'] += 1
                else:
                    history['late_payments'] += 1
        
        return history
    
    def get_user_risk_profile(self, user_id):  # ← THIS MUST BE INSIDE THE CLASS (same indentation as other methods)
        """Calculate risk profile based on history"""
        history = self.get_user_loan_history(user_id)
        
        # Get reputation tiers from config
        tiers = LOAN_CONFIG['reputation_tiers']
        
        if history['total_loans'] == 0:
            # New user - return ALL required fields
            new_tier = tiers['new']
            return {
                'risk_level': 'new',
                'risk_score': 100,
                'recommended_max_loan': new_tier['max_loan'],
                'interest_rate': new_tier['interest_rate'],
                'collateral_required': new_tier.get('collateral_required', False),
                'description': new_tier.get('description', '🌟 First-time borrower - Building trust'),
                'total_loans_completed': 0,
                'total_loans_defaulted': 0,
                'on_time_percentage': 100.0,
                'reputation': 100
            }
        
        # Calculate risk score (0-100)
        risk_score = 100
        
        # Penalty for defaults
        risk_score -= history['defaulted_loans'] * 50
        
        # Penalty for late payments
        risk_score -= history['late_payments'] * 10
        
        # Bonus for on-time payments
        risk_score += history['on_time_payments'] * 5
        
        # Ensure score stays within 0-100
        risk_score = max(0, min(100, risk_score))
        
        # Determine tier based on score
        tier = 'new'
        for tier_name, tier_config in tiers.items():
            if risk_score >= tier_config['min_score']:
                tier = tier_name
        
        tier_config = tiers[tier]
        
        # Calculate on-time percentage
        on_time_pct = (history['on_time_payments'] / max(1, history['total_loans'])) * 100
        
        return {
            'risk_level': tier,
            'risk_score': risk_score,
            'recommended_max_loan': tier_config['max_loan'],
            'interest_rate': tier_config['interest_rate'],
            'collateral_required': tier_config.get('collateral_required', False),
            'description': tier_config.get('description', f'{tier.title()} Member'),
            'total_loans_completed': history['completed_loans'],
            'total_loans_defaulted': history['defaulted_loans'],
            'on_time_percentage': on_time_pct,
            'reputation': risk_score
        }
    