"""Config - Load credentials from .env"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    ACCESS_TOKEN = os.getenv('ACCESS_TOKEN', '')
    API_KEY = os.getenv('API_KEY', '')
    API_SECRET = os.getenv('API_SECRET', '')
    
    @classmethod
    def validate(cls):
        if not cls.ACCESS_TOKEN:
            raise ValueError("ACCESS_TOKEN not set")
        return True
