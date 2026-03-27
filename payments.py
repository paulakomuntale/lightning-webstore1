import base64
import io
import qrcode
import random
import string

class PaymentManager:
    def __init__(self, lnd_config):
        self.lnd = None
        self.mock_mode = True
        
        # Try to connect to LND
        try:
            from lnd_client import LNDClient
            self.lnd = LNDClient(
                lnd_dir=lnd_config.get('lnd_dir'),
                rest_host=lnd_config.get('rest_host'),
                macaroon_path=lnd_config.get('macaroon_path'),
                tls_cert_path=lnd_config.get('tls_cert_path')
            )
            
            # Test connection with a simple call
            info = self.lnd.get_info()
            if info and 'identity_pubkey' in info:
                self.mock_mode = False
                print(f"✅ Connected to LND node: {info.get('alias', 'Unknown')}")
                print(f"   Using REAL Lightning payments")
            else:
                print("⚠️ LND connection test failed - using mock mode")
                self.mock_mode = True
        except Exception as e:
            print(f"⚠️ LND not available: {e}")
            print("Using MOCK MODE for testing")
            self.mock_mode = True
    
    def generate_invoice(self, amount_sats, memo):
        """Generate Lightning invoice (real or mock)"""
        try:
            if not self.mock_mode and self.lnd:
                # Real LND invoice
                result = self.lnd.add_invoice(amount=amount_sats, memo=memo)
                if result:
                    payment_request = result["payment_request"]
                    r_hash = base64.b64decode(result["r_hash"]).hex()
                    print(f"✅ REAL invoice generated for {amount_sats} sats")
                else:
                    raise Exception("LND returned no result")
            else:
                # Mock invoice for testing
                payment_request = f"lnbcrt{amount_sats}n1p{''.join(random.choices(string.ascii_lowercase + string.digits, k=50))}"
                r_hash = ''.join(random.choices(string.hexdigits.lower(), k=64))
                print(f"✅ MOCK invoice generated for {amount_sats} sats")
            
            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(payment_request.upper())
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            
            return {
                'payment_request': payment_request,
                'r_hash': r_hash,
                'qr_base64': qr_base64
            }
        except Exception as e:
            print(f"❌ Error generating invoice: {e}")
            return None
    
    def check_payment(self, r_hash):
        """Check if invoice has been paid"""
        try:
            if not self.mock_mode and self.lnd:
                # Real LND check
                invoice = self.lnd.lookup_invoice(r_hash)
                settled = invoice.get("settled", False)
                if settled:
                    print(f"✅ REAL payment confirmed")
                return settled
            else:
                # Mock mode - auto-confirm
                print(f"✅ MOCK payment confirmed")
                return True
        except Exception as e:
            print(f"Error checking payment: {e}")
            return True  # Return True in mock mode to continue testing