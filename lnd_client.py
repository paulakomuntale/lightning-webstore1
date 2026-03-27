import base64
import json
import ssl
import urllib.request
from pathlib import Path

class LNDClient:
    def __init__(self, lnd_dir=None, rest_host=None, macaroon_path=None, tls_cert_path=None):
        self.lnd_dir = Path(lnd_dir) if lnd_dir else None
        self.rest_host = rest_host.rstrip('/') if rest_host else "https://127.0.0.1:8083"
        
        print(f"🔌 Initializing LND Client...")
        print(f"   REST Host: {self.rest_host}")
        
        # Load TLS certificate
        if tls_cert_path and Path(tls_cert_path).exists():
            self.context = ssl.create_default_context(cafile=str(tls_cert_path))
            print(f"   TLS cert: {tls_cert_path}")
        elif self.lnd_dir and (self.lnd_dir / 'tls.cert').exists():
            tls_path = self.lnd_dir / 'tls.cert'
            self.context = ssl.create_default_context(cafile=str(tls_path))
            print(f"   TLS cert: {tls_path}")
        else:
            print("   ⚠️ TLS cert not found, using unverified context")
            self.context = ssl._create_unverified_context()
        
        # Load macaroon - IMPORTANT: Send as hex, not base64
        macaroon_hex = None
        if macaroon_path and Path(macaroon_path).exists():
            with open(macaroon_path, 'rb') as f:
                macaroon_bytes = f.read()
                # LND expects the macaroon as a hex string
                macaroon_hex = macaroon_bytes.hex()
            print(f"   Macaroon loaded: {macaroon_path}")
        elif self.lnd_dir and (self.lnd_dir / 'data/chain/bitcoin/regtest/admin.macaroon').exists():
            macaroon_file = self.lnd_dir / 'data/chain/bitcoin/regtest/admin.macaroon'
            with open(macaroon_file, 'rb') as f:
                macaroon_bytes = f.read()
                macaroon_hex = macaroon_bytes.hex()
            print(f"   Macaroon loaded: {macaroon_file}")
        else:
            print("   ⚠️ No macaroon found. LND authentication may fail.")
        
        # Store macaroon as hex string
        self.macaroon_hex = macaroon_hex
        
        # Test connection
        print("   Testing connection...")
        info = self.get_info()
        if info:
            print(f"   ✅ Connected to LND node: {info.get('alias', 'Unknown')}")
            print(f"   Block Height: {info.get('block_height', 'Unknown')}")
            print(f"   Active Channels: {info.get('num_active_channels', 0)}")
        else:
            print("   ❌ Failed to connect to LND")
    
    def _request(self, endpoint, method='GET', data=None):
        """Make HTTP request to LND REST API"""
        url = f"{self.rest_host}/v1/{endpoint}"
        
        headers = {}
        # LND expects the macaroon as a hex string in the header
        if self.macaroon_hex:
            headers['Grpc-Metadata-macaroon'] = self.macaroon_hex
        
        if data:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(data).encode()
        
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        
        try:
            with urllib.request.urlopen(req, context=self.context) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            print(f"HTTP Error {e.code}: {e.reason}")
            if e.code == 401:
                print("   Authentication failed - check macaroon format")
                print(f"   Macaroon length: {len(self.macaroon_hex) if self.macaroon_hex else 0}")
            return None
        except urllib.error.URLError as e:
            print(f"URL Error: {e.reason}")
            return None
        except Exception as e:
            print(f"Error calling {endpoint}: {e}")
            return None
    
    def add_invoice(self, amount, memo):
        """Create a Lightning invoice"""
        invoice_data = {
            'value': amount,
            'memo': memo,
            'expiry': 3600
        }
        print(f"📝 Creating invoice for {amount} sats: {memo}")
        result = self._request('invoices', method='POST', data=invoice_data)
        if result:
            print(f"   ✅ Invoice created")
        return result
    
    def lookup_invoice(self, r_hash):
        """Check invoice status"""
        # Convert hex to base64 for LND
        if len(r_hash) == 64:
            r_hash_bytes = bytes.fromhex(r_hash)
            r_hash_b64 = base64.b64encode(r_hash_bytes).decode()
        else:
            r_hash_b64 = r_hash
        
        result = self._request(f'invoice/{r_hash_b64}')
        if result:
            settled = result.get("settled", False)
            if settled:
                print(f"   ✅ Invoice paid!")
        return result if result else {'settled': False}
    
    def get_info(self):
        """Get node info"""
        return self._request('getinfo')
    
    def channel_balance(self):
        """Get channel balance"""
        return self._request('balance/channels')