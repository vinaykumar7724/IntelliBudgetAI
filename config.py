import os
from dotenv import load_dotenv

# load environment variables from a .env file if present
# use override=True so that values in .env replace any existing shell variables
print('CWD before dotenv:', os.getcwd())
print('Directory listing:', os.listdir())
load_dotenv(override=True)

# dotenv may not override existing system variables; if DATABASE_URL still default
# try manual parse of .env file in project root to ensure correct value.
if os.environ.get('DATABASE_URL') in (None, '', 'mysql://username:password@localhost/intellibudget'):
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    try:
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith('DATABASE_URL'):
                    key, val = line.split('=', 1)
                    os.environ['DATABASE_URL'] = val.strip()
                    print('MANUALLY SET DATABASE_URL:', os.environ['DATABASE_URL'])
                    break
    except FileNotFoundError:
        pass

# show debug after attempts
print('FINAL environment DATABASE_URL:', os.environ.get('DATABASE_URL'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'you-will-never-guess')

    # read database URL from environment and handle quoting of special characters
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        # URL-encode password if necessary
        from urllib.parse import urlparse, quote_plus, urlunparse
        parsed = urlparse(db_url)
        if parsed.password:
            # quote the password portion to avoid parsing issues
            quoted_pwd = quote_plus(parsed.password)
            # reconstruct netloc (user:pass@host:port)
            if parsed.username:
                user_part = parsed.username
                if parsed.port:
                    host_part = f"{parsed.hostname}:{parsed.port}"
                else:
                    host_part = parsed.hostname or ''
                netloc = f"{user_part}:{quoted_pwd}@{host_part}"
            else:
                netloc = parsed.netloc.replace(parsed.password, quoted_pwd)
            parsed = parsed._replace(netloc=netloc)
            db_url = urlunparse(parsed)
    else:
        raise RuntimeError('DATABASE_URL must be set in environment or .env')

    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

# additional config values can be added here
