import os
import midtransclient

MIDTRANS_SERVER_KEY = os.environ.get('YOUR_MIDTRANS_SERVER_KEY')
MIDTRANS_CLIENT_KEY = os.environ.get('YOUR_MIDTRANS_CLIENT_KEY')

midtrans_core_api = midtransclient.CoreApi(
    is_production=False, 
    server_key=MIDTRANS_SERVER_KEY, 
    client_key=MIDTRANS_CLIENT_KEY  
)

snap = midtransclient.Snap(
    is_production=False, 
    server_key=MIDTRANS_SERVER_KEY, 
    client_key=MIDTRANS_CLIENT_KEY  
)

print("Server Key:", MIDTRANS_SERVER_KEY)