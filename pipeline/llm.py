"""Free-tier LLM access: Gemini (free API key), Groq (free API key), or local Ollama."""
from __future__ import annotations

import json
import os
import re

import requests


def _extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    start = text.find("{")
    end = text.rfind("}")
    return json.loads(text[start:end + 1])


def _github(prompt, system, model):
    """GitHub Models: free, uses the workflow's own GITHUB_TOKEN (needs `models: read`)."""
    body = {"model": model, "temperature": 0.9,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
    errors = []
    for url, m in (("https://models.github.ai/inference/chat/completions", model),
                   ("https://models.inference.ai.azure.com/chat/completions", model.split("/")[-1])):
        try:
            r = requests.post(url, json={**body, "model": m}, timeout=120, headers={
                "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Content-Type": "application/json",
                "Accept": "application/json"})
            if r.status_code != 200 or not r.text.strip():
                errors.append(f"{url} -> HTTP {r.status_code}: {r.text[:300]!r}")
                continue
            try:
                content = r.json()["choices"][0]["message"]["content"]
            except ValueError:
                errors.append(f"{url} -> non-JSON 200 ({r.headers.get('content-type')}): {r.text[:300]!r}")
                continue
            if content:
                return content
            errors.append(f"{url} -> empty content")
        except Exception as ex:
            errors.append(f"{url} -> {ex}")
    raise RuntimeError(" | ".join(errors))


def _gemini(prompt, system, model):
    key = os.environ["GEMINI_API_KEY"]
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key},
        json={"systemInstruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9}},
        timeout=120)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _groq(prompt, system, model):
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={"model": model, "temperature": 0.9, "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
        timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _ollama(prompt, system, model):
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    r = requests.post(f"{host}/api/chat", json={
        "model": model, "format": "json", "stream": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
        timeout=600)
    r.raise_for_status()
    return r.json()["message"]["content"]


def complete_json(prompt: str, system: str, cfg: dict) -> dict:
    errors = []
    for p in cfg.get("providers", ["github", "gemini", "groq", "ollama"]):
        try:
            if p == "github" and os.environ.get("GITHUB_TOKEN"):
                return _extract_json(_github(prompt, system, cfg.get("github_model", "openai/gpt-4o-mini")))
            if p == "gemini" and os.environ.get("GEMINI_API_KEY"):
                return _extract_json(_gemini(prompt, system, cfg.get("gemini_model", "gemini-flash-latest")))
            if p == "groq" and os.environ.get("GROQ_API_KEY"):
                return _extract_json(_groq(prompt, system, cfg.get("groq_model", "llama-3.3-70b-versatile")))
            if p == "ollama" and os.environ.get("OLLAMA_HOST"):
                return _extract_json(_ollama(prompt, system, cfg.get("ollama_model", "llama3.1")))
        except Exception as ex:
            errors.append(f"{p}: {ex}")
    raise RuntimeError("No LLM provider worked (GitHub Models / Gemini / Groq). " + "; ".join(errors))
