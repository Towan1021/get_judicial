import os
import json
import requests
import psycopg2
import psycopg2.extras
import datetime
import logging
import time
from typing import Any, Dict, List, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging with correct format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('judicial-api')

# Load config from environment for security
DB_CONFIG = {
    "host": 'pgm-1ud0o57e5ux48t71zo.pg.rds.aliyuncs.com',
    "port": 5432,
    "database": 'lawbot',
    "user": 'lawbotgeneral',
    "password": os.environ.get('DB_PASSWORD', 'password')
}

# API Endpoints
BASE_URL = "https://data.judicial.gov.tw/jdg/api"
AUTH_ENDPOINT = f"{BASE_URL}/Auth"
LIST_ENDPOINT = f"{BASE_URL}/JList"
DOC_ENDPOINT = f"{BASE_URL}/JDoc"

# Credentials - primary and backup
API_CREDENTIALS = [
    {'user': 'alex', 'password': 'alex891021'},
    {'user': 'lawbot', 'password': 'lawbot1021'}
]

def create_session_with_retries():
    """Create a requests session with retry strategy"""
    session = requests.Session()
    
    # Define retry strategy
    retry_strategy = Retry(
        total=10,  # Total number of retries
        backoff_factor=2,  # Wait time between retries (exponential backoff)
        status_forcelist=[429, 500, 502, 503, 504],  # HTTP status codes to retry
        allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
    )
    
    # Mount adapter with retry strategy
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Set reasonable timeouts
    session.timeout = (10, 30)  # (connection timeout, read timeout)
    
    return session

def wait_with_exponential_backoff(attempt: int, max_wait: int = 60):
    """Wait with exponential backoff"""
    wait_time = min(2 ** attempt, max_wait)
    logger.info(f"Waiting {wait_time} seconds before retry...")
    time.sleep(wait_time)

# Database connection helper
def get_db_connection(retries: int = 3, delay: int = 2) -> psycopg2.extensions.connection:
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"DB connect attempt {attempt}/{retries}")
            return psycopg2.connect(**DB_CONFIG)
        except psycopg2.OperationalError as e:
            logger.warning(f"DB connect failed (attempt {attempt}): {e}")
            if attempt < retries:
                time.sleep(delay)
            else:
                logger.error("Exceeded DB connection retries.")
                raise

def request_token(max_retries: int = 10) -> str:
    session = create_session_with_retries()
    
    # Try each credential set
    for cred_index, credentials in enumerate(API_CREDENTIALS):
        logger.info(f"Trying credentials set {cred_index + 1}/{len(API_CREDENTIALS)} (user: {credentials['user']})")
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Requesting auth token with {credentials['user']} (attempt {attempt}/{max_retries})")
                
                resp = session.post(
                    AUTH_ENDPOINT,
                    json={'user': credentials['user'], 'password': credentials['password']},
                    timeout=(10, 30)
                )
                resp.raise_for_status()
                data = resp.json()
                
                if 'error' in data:
                    raise RuntimeError(f"Auth error: {data['error']}")
                    
                token = data.get('token') or data.get('Token')
                if not token:
                    raise RuntimeError("No token in auth response")
                    
                logger.info(f"Auth token obtained successfully with {credentials['user']}")
                return token
                
            except (requests.exceptions.ConnectionError, 
                    requests.exceptions.Timeout) as e:
                logger.warning(f"Network error on attempt {attempt} with {credentials['user']}: {e}")
                if attempt < max_retries:
                    wait_with_exponential_backoff(attempt)
                else:
                    logger.error(f"Max retries exceeded for {credentials['user']}")
                    break  # Break inner loop to try next credential set
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error with {credentials['user']}: {e}")
                break  # Break inner loop to try next credential set
            except Exception as e:
                logger.error(f"Unexpected error with {credentials['user']}: {e}")
                break  # Break inner loop to try next credential set
    
    # If we get here, all credential sets failed
    raise RuntimeError(f"Failed to get token with all credential sets after {max_retries} attempts each")

def fetch_list(token: str, max_retries: int = 5) -> List[Dict[str, Any]]:
    session = create_session_with_retries()
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Fetching document list (attempt {attempt}/{max_retries})")
            
            resp = session.post(
                LIST_ENDPOINT,
                json={'token': token},
                timeout=(10, 30)
            )
            resp.raise_for_status()
            data = resp.json()
            
            if isinstance(data, dict) and 'error' in data:
                raise RuntimeError(f"List API error: {data['error']}")
            if not isinstance(data, list):
                raise RuntimeError(f"Unexpected list response: {data}")
                
            logger.info(f"Document list fetched successfully ({len(data)} items)")
            return data
            
        except (requests.exceptions.ConnectionError, 
                requests.exceptions.Timeout) as e:
            logger.warning(f"Network error on attempt {attempt}: {e}")
            if attempt < max_retries:
                wait_with_exponential_backoff(attempt)
            else:
                logger.error("Max retries exceeded for list request")
                raise RuntimeError(f"Failed to fetch list after {max_retries} attempts: {e}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            raise RuntimeError(f"HTTP error during list fetch: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise RuntimeError(f"Unexpected error during list fetch: {e}")

# DB operations unchanged
def upsert_jids(jids: List[str]) -> None:
    if not jids:
        return
    values = [(jid, '存') for jid in jids]
    query = (
        "INSERT INTO judicial_documents (jid, status) VALUES %s "
        "ON CONFLICT (jid) DO NOTHING"
    )
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, query, values)
        conn.commit()

def upsert_documents(docs: List[Dict[str, Any]]):
    if not docs:
        return
    records = []
    for d in docs:
        records.append(
            (
                d.get('JID', ''),
                d.get('JYEAR', ''),
                d.get('JCASE', ''),
                d.get('JNO', ''),
                d.get('JDATE', ''),
                d.get('JTITLE', ''),
                d.get('JFULLX', {}).get('JFULLTYPE', ''),
                d.get('JFULLX', {}).get('JFULLCONTENT', ''),
                d.get('JFULLX', {}).get('JFULLPDF', ''),
                json.dumps(d.get('ATTACHMENTS', [])),
                '存'
            )
        )
    query = (
        "INSERT INTO judicial_documents "
        "(jid, jyear, jcase, jno, jdate, jtitle, jfulltype, jfullcontent, jfullpdf, attachments, status) "
        "VALUES %s "
        "ON CONFLICT (jid) DO UPDATE SET "
        "jyear=EXCLUDED.jyear, jcase=EXCLUDED.jcase, jno=EXCLUDED.jno, jdate=EXCLUDED.jdate, "
        "jtitle=EXCLUDED.jtitle, jfulltype=EXCLUDED.jfulltype, jfullcontent=EXCLUDED.jfullcontent, "
        "jfullpdf=EXCLUDED.jfullpdf, attachments=EXCLUDED.attachments, status='存'"
    )
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, query, records, page_size=100)
        conn.commit()

def mark_removed(jid: str):
    query = "UPDATE judicial_documents SET status='廢' WHERE jid=%s"
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (jid,))
        conn.commit()

# Main function
def process_judicial_documents():
    try:
        logger.info("Starting judicial document processing")
        
        # Test network connectivity first
        try:
            import socket
            socket.getaddrinfo('data.judicial.gov.tw', 443)
            logger.info("DNS resolution test passed")
        except socket.gaierror as e:
            logger.warning(f"DNS resolution test failed: {e}")
            # Continue anyway as this might be temporary
        
        token = request_token()
        lst = fetch_list(token)
        
    except RuntimeError as e:
        logger.error(f"Initialization error: {e}")
        return json.dumps({'status': 'error', 'message': str(e)})
    except Exception as e:
        logger.error(f"Unexpected error during initialization: {e}")
        return json.dumps({'status': 'error', 'message': f'Unexpected error: {str(e)}'})

    try:
        all_jids = []
        for day in lst:
            key = 'LIST' if 'LIST' in day else 'list'
            all_jids.extend(day.get(key, []))

        logger.info(f"Found {len(all_jids)} judicial document IDs")
        
        if all_jids:
            upsert_jids(all_jids)
            logger.info(f"Successfully processed {len(all_jids)} document IDs")
        else:
            logger.warning("No document IDs found to process")

        result = {
            'status': 'success',
            'processed': len(all_jids),
            'timestamp': datetime.datetime.now().isoformat()
        }
        logger.info(f"Run completed successfully: {result}")
        return json.dumps(result)
        
    except Exception as e:
        logger.error(f"Error during document processing: {e}")
        return json.dumps({
            'status': 'error', 
            'message': f'Processing error: {str(e)}',
            'timestamp': datetime.datetime.now().isoformat()
        })

if __name__ == "__main__":
    result = process_judicial_documents()
    print(result)
