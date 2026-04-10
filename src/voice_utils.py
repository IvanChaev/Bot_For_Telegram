# src/voice_utils.py
import asyncio
import subprocess
import sys
import os
import tempfile
import io
import logging
import aiohttp
from telegram.error import NetworkError, TimedOut
import edge_tts
import whisper
from .config import VOICE_NAME, MODEL_NAME, OLLAMA_GENERATE

logger = logging.getLogger(__name__)

whisper_model = None

def init_whisper():
    global whisper_model
    if whisper_model is None:
        logger.info("Загружаю модель Whisper (base)...")
        whisper_model = whisper.load_model("base")
        logger.info("Whisper готов.")
    return whisper_model

async def generate_voice(text: str, timeout: int = 30) -> bytes:
    clean_text = text.replace('*', '').replace('#', '')
    def _sync_generate():
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_mp3:
            mp3_path = tmp_mp3.name
        ogg_path = None
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.run([
                "edge-tts", "--voice", VOICE_NAME, "--text", clean_text, "--write-media", mp3_path
            ], check=True, capture_output=True, creationflags=creationflags, timeout=timeout)
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_ogg:
                ogg_path = tmp_ogg.name
            subprocess.run([
                "ffmpeg", "-i", mp3_path,
                "-c:a", "libopus", "-b:a", "32k",
                "-vbr", "on", "-compression_level", "10",
                "-application", "voip", "-y",
                "-loglevel", "quiet",
                ogg_path
            ], check=True, capture_output=True, creationflags=creationflags, timeout=timeout)
            with open(ogg_path, "rb") as f:
                ogg_data = f.read()
            return ogg_data
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"Ошибка в subprocess: {error_msg}")
            raise RuntimeError(f"Voice generation failed: {error_msg}")
        except subprocess.TimeoutExpired:
            logger.error(f"Subprocess timeout after {timeout} seconds")
            raise RuntimeError(f"Voice generation timeout")
        finally:
            try:
                os.unlink(mp3_path)
            except:
                pass
            if ogg_path:
                try:
                    os.unlink(ogg_path)
                except:
                    pass
    try:
        return await asyncio.wait_for(asyncio.to_thread(_sync_generate), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"Генерация голоса превысила таймаут {timeout} секунд")
        raise RuntimeError("Voice generation async timeout")

async def transcribe_voice(ogg_bytes: bytes, timeout: int = 60) -> str:
    model = init_whisper()
    def _sync_transcribe():
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_ogg:
            tmp_ogg.write(ogg_bytes)
            ogg_path = tmp_ogg.name
        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                wav_path = tmp_wav.name
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.run([
                "ffmpeg", "-i", ogg_path,
                "-ar", "16000", "-ac", "1", "-y",
                "-loglevel", "quiet",
                wav_path
            ], check=True, capture_output=True, creationflags=creationflags, timeout=timeout)
            result = model.transcribe(wav_path, language="ru", fp16=False)
            text = result["text"].strip()
            return text
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"FFmpeg error: {error_msg}")
            raise RuntimeError(f"Audio conversion failed: {error_msg}")
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timeout after {timeout} seconds")
            raise RuntimeError(f"Audio conversion timeout")
        finally:
            try:
                os.unlink(ogg_path)
            except:
                pass
            if wav_path:
                try:
                    os.unlink(wav_path)
                except:
                    pass
    try:
        return await asyncio.wait_for(asyncio.to_thread(_sync_transcribe), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"Распознавание голоса превысило таймаут {timeout} секунд")
        raise RuntimeError("Transcription async timeout")

async def send_voice_with_retry(bot, chat_id, voice_data, max_retries=3):
    for attempt in range(max_retries):
        try:
            await bot.send_voice(chat_id=chat_id, voice=io.BytesIO(voice_data))
            return
        except (NetworkError, TimedOut) as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            logger.warning(f"Таймаут отправки голоса, попытка {attempt+1}/{max_retries}. Жду {wait} сек...")
            await asyncio.sleep(wait)

async def clear_model_cache():
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"model": MODEL_NAME, "keep_alive": 0}
            async with session.post(OLLAMA_GENERATE, json=payload) as resp:
                if resp.status == 200:
                    logger.info(f"Модель {MODEL_NAME} выгружена из памяти.")
    except Exception as e:
        logger.warning(f"Не удалось выгрузить модель: {e}")