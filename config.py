import os

# LND Configuration - Connect to your Polar node (Bob)
LND_CONFIG = {
    'node_name': 'bob',
    'lnd_dir': os.path.expanduser('C:\\Users\\lenovo\\.polar\\networks\\2\\volumes\\lnd\\bob'),
    'rest_host': 'https://127.0.0.1:8083',  # Bob's REST port
    'macaroon_path': os.path.expanduser('C:\\Users\\lenovo\\.polar\\networks\\2\\volumes\\lnd\\bob\\data\\chain\\bitcoin\\regtest\\admin.macaroon'),
    'tls_cert_path': os.path.expanduser('C:\\Users\\lenovo\\.polar\\networks\\2\\volumes\\lnd\\bob\\tls.cert')
}

# Loan Configuration
LOAN_CONFIG = {
    'min_loan': 5000,
    'max_loan': 500000,
    'interest_rate': 2,
    'min_days': 7,
    'max_days': 30,
    'late_fee': 5,
    
    'reputation_tiers': {
        'new': {
            'min_score': 0,
            'max_loan': 50000,
            'interest_rate': 5,
            'collateral_required': False,
            'description': '🌟 First-time borrower - Building trust'
        },
        'bronze': {
            'min_score': 60,
            'max_loan': 100000,
            'interest_rate': 3,
            'collateral_required': False,
            'description': '🥉 Bronze Member - Reliable borrower'
        },
        'silver': {
            'min_score': 70,
            'max_loan': 250000,
            'interest_rate': 2.5,
            'collateral_required': False,
            'description': '🥈 Silver Member - Trusted borrower'
        },
        'gold': {
            'min_score': 80,
            'max_loan': 500000,
            'interest_rate': 2,
            'collateral_required': False,
            'description': '🥇 Gold Member - Premium borrower'
        },
        'platinum': {
            'min_score': 90,
            'max_loan': 1000000,
            'interest_rate': 1.5,
            'collateral_required': False,
            'description': '💎 Platinum Member - Elite borrower'
        }
    }
}

# App Configuration
APP_CONFIG = {
    'name': 'Lightning Micro-Lend',
    'host': '127.0.0.1',
    'port': 5002,
    'debug': True,
}