#!/usr/bin/env python3
"""
AGENT SHORTS MACHINE — DropAtom YouTube Shorts Automation
===========================================================
Automated YouTube Shorts pipeline for dropshipping traffic.

Inspired by Earn It Media (Tabassum @Tabbu_ai) analysis — divergent approach:
  - Tabassum: 1 channel × manual × 3-4h/video → $1-5K/mo
  - DropAtom:  5 channels × automated × 15min compute → $5-25K/mo

Pipeline:
  1. TREND DETECT   — Find viral trends (YouTube Shorts + TikTok)
  2. CLIP DOWNLOAD  — Download source clips (yt-dlp)
  3. SCRIPT GEN     — Generate curiosity-driven script (LLM)
  4. VOICEOVER      — Generate TTS audio (edge-tts, free)
  5. VIDEO ASSEMBLE — Assemble short with ffmpeg (clips + voice + subs + overlays)
  6. POST           — Upload to YouTube (API or manual)
  7. ANALYZE        — Track performance (swipe rate, APV, views)

Key insight from Tabassum (formalized):
  "Curiosity gap" = the ONLY viral signal that matters
  → We score it 0-100 before producing anything

Usage:
  python3 shorts_machine.py --mode trend                     # Find trends
  python3 shorts_machine.py --mode trend --niche "beauty"    # Niche-specific trends
  python3 shorts_machine.py --mode produce --trend "owl"     # Produce a short
  python3 shorts_machine.py --mode produce --product "..."   # Product-focused short
  python3 shorts_machine.py --mode batch --count 5           # Batch produce 5 shorts
  python3 shorts_machine.py --mode full                      # Full pipeline (trend → video)
  python3 shorts_machine.py --mode analyze                   # Analyze existing shorts performance
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
SHORTS_DIR = OUTPUT_DIR / "shorts"
PRODUCTS_FILE = STATE_DIR / "products.json"
JOURNAL_DIR = STATE_DIR / "journal"
TRENDS_FILE = STATE_DIR / "shorts-trends.json"
CHANNELS_FILE = STATE_DIR / "shorts-channels.json"

HERMES_ENV = Path.home() / ".hermes" / ".env"

# Curiosity triggers (from Tabassum analysis)
CURIOSITY_TRIGGERS = [
    "how did they", "you won't believe", "the method will shock",
    "wait until the end", "the last person", "nobody expected",
    "this trick", "secret method", "exposed", "revealed",
    "impossible", "how is this", "what happens next",
    "i can't believe", "this changed everything",
]

# Viral script templates (Tabassum's winning structure, formalized)
SCRIPT_TEMPLATES = {
    "curiosity_gap": (
        "This {subject} tried the {trend} where {hook_description} "
        "and while most people thought {misdirection}, "
        "the last {reveal_person} showed exactly how to do it "
        "and the {reveal_element} will shock you."
    ),
    "product_demo": (
        "I didn't believe this {product} would actually {benefit} "
        "but after {timeframe} of using it, "
        "the results speak for themselves. "
        "Here's exactly what happened..."
    ),
    "myth_buster": (
        "Everyone says you need to {expensive_thing} to get {result}. "
        "This {product} costs {price} and does the exact same thing. "
        "Here's the proof."
    ),
    "confessional": (
        "I was the person who {embarrassing_habit} "
        "until my {relation} showed me this {product}. "
        "Now I {transformed_state} "
        "and honestly I'm mad I didn't find it sooner."
    ),
    "challenge": (
        "Day {number} of using only this {product} to {goal}. "
        "{before_state} → {after_state}. "
        "The results are {intensity_descriptor}."
    ),
}

LLM_CHAIN = [
    "minimax-m2.5:free",
    "google/gemma-4-31b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
]

_active_model = None


def load_env():
    if HERMES_ENV.exists():
        for line in HERMES_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())


load_env()
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY', '')


# ─── LLM ─────────────────────────────────────────────────────────────

def get_active_model():
    global _active_model
    if _active_model:
        return _active_model
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    for model in LLM_CHAIN:
        try:
            resp = client.chat.completions.create(
                model=model, messages=[{'role': 'user', 'content': 'OK'}], max_tokens=5)
            _active_model = model
            return model
        except:
            continue
    return None


def llm(prompt: str, system: str = "", max_tokens: int = 1000) -> str:
    if not OPENROUTER_KEY:
        return ""
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    model = get_active_model()
    if not model:
        return ""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=0.8)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if '429' in str(e):
                time.sleep(8 * (attempt + 1))
                for m in LLM_CHAIN:
                    if m != model:
                        try:
                            resp = client.chat.completions.create(
                                model=m, messages=messages,
                                max_tokens=max_tokens, temperature=0.8)
                            global _active_model
                            _active_model = m
                            model = m
                            return resp.choices[0].message.content.strip()
                        except:
                            continue
            else:
                break
    return ""


# ─── Data Models ─────────────────────────────────────────────────────

@dataclass
class Trend:
    """A detected viral trend."""
    name: str = ""
    niche: str = ""
    description: str = ""
    source_url: str = ""
    source_views: int = 0
    curiosity_score: int = 0          # 0-100 (formalized from Tabassum)
    saturation: float = 0.0           # 0-1 (lower = better)
    recency_hours: int = 0
    clip_urls: list = field(default_factory=list)
    hashtags: list = field(default_factory=list)
    detected_at: str = ""
    
    @property
    def viral_potential(self) -> float:
        """Composite score: curiosity × views × (1 - saturation) × recency bonus"""
        recency_bonus = max(0, 1.0 - (self.recency_hours / 168))  # 7-day decay
        return (self.curiosity_score / 100) * (min(self.source_views, 10_000_000) / 10_000_000) * (1 - self.saturation) * recency_bonus


@dataclass
class ShortVideo:
    """A produced YouTube Short."""
    id: str = ""
    trend_name: str = ""
    channel: str = ""
    script: str = ""
    audio_path: str = ""
    video_path: str = ""
    thumbnail_path: str = ""
    duration_sec: float = 0.0
    curiosity_score: int = 0
    template_used: str = ""
    product_name: str = ""
    product_link: str = ""
    status: str = "draft"              # draft → produced → posted → analyzed
    posted_at: str = ""
    views: int = 0
    swipe_rate: float = 0.0           # 0-1 (target 0.80+)
    apv: float = 0.0                  # Average Percentage Viewed (target 100%+)
    created_at: str = ""


@dataclass
class Channel:
    """A YouTube Shorts channel managed by DropAtom."""
    name: str = ""
    handle: str = ""
    niche: str = ""
    status: str = "warmup"            # warmup → active → monetized → scaled
    videos_posted: int = 0
    total_views: int = 0
    monetized: bool = False
    avg_swipe_rate: float = 0.0
    avg_apv: float = 0.0
    zero_view_count: int = 0
    created_at: str = ""


# ─── Phase 1: Trend Detection ───────────────────────────────────────

def score_curiosity(text: str) -> int:
    """Score a text's curiosity gap potential (0-100).
    
    Based on Tabassum's insight: "how are they doing this?" = viral signal.
    We formalize it as:
    - Information gap questions (+30)
    - Visual impossibility words (+20)
    - Reveal/tease structure (+20)
    - Emotional intensity (+15)
    - Brevity efficiency (+15)
    """
    text_lower = text.lower()
    score = 20  # base
    
    # Information gap markers
    gap_words = ["how", "why", "what happens", "secret", "method", "trick", "exposed", "revealed"]
    for w in gap_words:
        if w in text_lower:
            score += 8
    
    # Visual impossibility
    impossible_words = ["impossible", "float", "disappear", "invisible", "defy", "glitch"]
    for w in impossible_words:
        if w in text_lower:
            score += 10
    
    # Reveal structure
    if "last" in text_lower and ("show" in text_lower or "shock" in text_lower):
        score += 15
    if "wait until" in text_lower:
        score += 10
    
    # Emotional intensity
    emotion_words = ["shock", "crazy", "insane", "unbelievable", "mind-blowing", "changed"]
    for w in emotion_words:
        if w in text_lower:
            score += 5
    
    # Brevity (shorter = better for shorts)
    word_count = len(text_lower.split())
    if word_count < 30:
        score += 10
    elif word_count < 50:
        score += 5
    
    return min(score, 100)


def detect_trends(niche: str = "", max_trends: int = 10) -> list[Trend]:
    """Detect viral trends via YouTube Shorts scraping + LLM analysis.
    
    Uses yt-dlp to scrape shorts feed, then LLM to identify patterns.
    """
    trends = []
    
    print(f"\n🔍 Detecting trends" + (f" in niche: {niche}" if niche else ""))
    
    # Search YouTube Shorts for trending content
    search_queries = [f"#shorts trending {niche}", f"#{niche} trend 2026"] if niche else [
        "#shorts trending", "viral trend 2026 shorts", "dance trend shorts",
    ]
    
    raw_videos = []
    for query in search_queries[:2]:
        try:
            cmd = [
                "yt-dlp", "--flat-playlist", "-j",
                f"ytsearch10:{query}",
                "--playlist-end", "10",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    v = json.loads(line)
                    title = v.get('title', '')
                    views = v.get('view_count', 0) or 0
                    raw_videos.append({
                        'title': title,
                        'views': views,
                        'url': v.get('webpage_url', ''),
                        'duration': v.get('duration', 0),
                        'uploader': v.get('uploader', ''),
                    })
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            print(f"  ⚠️  Search error: {str(e)[:60]}")
    
    if not raw_videos:
        print("  ⚠️  No videos found. Using LLM trend generation as fallback.")
        return _generate_trends_llm(niche, max_trends)
    
    # Filter for shorts (< 60s) and sort by views
    shorts = [v for v in raw_videos if (v['duration'] or 999) < 60]
    shorts.sort(key=lambda x: x['views'], reverse=True)
    
    print(f"  Found {len(shorts)} shorts, analyzing...")
    
    # Score each for curiosity
    for v in shorts[:max_trends * 2]:
        curiosity = score_curiosity(v['title'])
        if curiosity >= 40:
            trends.append(Trend(
                name=v['title'][:80],
                niche=niche or "general",
                description=v['title'],
                source_url=v['url'],
                source_views=v['views'],
                curiosity_score=curiosity,
                recency_hours=1,  # rough estimate
                detected_at=datetime.now(timezone.utc).isoformat(),
            ))
    
    # Sort by viral potential
    trends.sort(key=lambda t: t.viral_potential, reverse=True)
    trends = trends[:max_trends]
    
    # Use LLM to enhance trend analysis
    if trends:
        trend_list = "\n".join([f"- {t.name} (curiosity: {t.curiosity_score})" for t in trends])
        prompt = f"""Analyze these YouTube Shorts trends and for each one:
1. Extract the core curiosity hook (what makes people watch?)
2. Rate saturation (0.0-1.0, lower = less saturated)
3. Suggest 3 spin ideas that add originality

Trends:
{trend_list}

Return JSON array with keys: name, curiosity_hook, saturation, spin_ideas (array of 3 strings)"""
        
        llm_result = llm(prompt, system="You are a YouTube Shorts viral analyst. Return only valid JSON.", max_tokens=1500)
        
        # Parse LLM enhancement
        try:
            # Extract JSON from response
            json_match = re.search(r'\[.*\]', llm_result, re.DOTALL)
            if json_match:
                enhanced = json.loads(json_match.group())
                for i, e in enumerate(enhanced):
                    if i < len(trends):
                        trends[i].description += f" | Hook: {e.get('curiosity_hook', '')}"
                        trends[i].saturation = float(e.get('saturation', 0.5))
        except (json.JSONDecodeError, ValueError):
            pass
    
    # Save trends
    _save_trends(trends)
    
    for i, t in enumerate(trends):
        print(f"  {i+1}. [{t.curiosity_score}⚡] {t.name[:60]} ({t.source_views:,} views, sat: {t.saturation:.1f})")
    
    return trends


def _generate_trends_llm(niche: str, count: int) -> list[Trend]:
    """Fallback: Generate trend ideas via LLM when scraping fails."""
    prompt = f"""Generate {count} YouTube Shorts trend ideas for the niche "{niche or 'general'}".
    
For each trend, provide:
- A catchy title that creates a curiosity gap
- The curiosity hook (what makes people watch?)
- Estimated saturation (0.0-1.0)
- 3 clip search keywords to find source material

Return JSON array with: title, curiosity_hook, saturation, search_keywords"""
    
    result = llm(prompt, system="You are a YouTube Shorts expert. Return only valid JSON.", max_tokens=1500)
    
    trends = []
    try:
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            items = json.loads(json_match.group())
            for item in items:
                c_score = score_curiosity(item.get('title', '') + ' ' + item.get('curiosity_hook', ''))
                trends.append(Trend(
                    name=item.get('title', 'Unknown'),
                    niche=niche or "general",
                    description=f"Hook: {item.get('curiosity_hook', '')}",
                    curiosity_score=c_score,
                    saturation=float(item.get('saturation', 0.5)),
                    hashtags=item.get('search_keywords', []),
                    detected_at=datetime.now(timezone.utc).isoformat(),
                ))
    except (json.JSONDecodeError, ValueError):
        pass
    
    trends.sort(key=lambda t: t.viral_potential, reverse=True)
    _save_trends(trends)
    return trends


def _save_trends(trends: list[Trend]):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = [asdict(t) for t in trends]
    TRENDS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_trends() -> list[Trend]:
    if not TRENDS_FILE.exists():
        return []
    data = json.loads(TRENDS_FILE.read_text())
    return [Trend(**d) for d in data]


# ─── Phase 2: Clip Download ─────────────────────────────────────────

def download_clips(trend: Trend, output_dir: Path, max_clips: int = 5) -> list[Path]:
    """Download source clips for a trend using yt-dlp."""
    output_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    
    # Search for clips related to this trend
    search_terms = [trend.name[:50]]
    if trend.hashtags:
        search_terms = trend.hashtags[:2]
    
    for term in search_terms:
        try:
            cmd = [
                "yt-dlp", "--flat-playlist", "-j",
                f"ytsearch{max_clips}:{term} short",
                "--playlist-end", str(max_clips),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            video_urls = []
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    v = json.loads(line)
                    url = v.get('webpage_url', '')
                    dur = v.get('duration', 999)
                    if url and dur and dur < 60:
                        video_urls.append(url)
                except json.JSONDecodeError:
                    continue
            
            for url in video_urls[:max_clips]:
                clip_file = output_dir / f"clip_{len(clips):03d}.mp4"
                if clip_file.exists():
                    clips.append(clip_file)
                    continue
                try:
                    subprocess.run([
                        "yt-dlp", "-f", "best[height<=720]", "--max-filesize", "50M",
                        "-o", str(clip_file), url
                    ], capture_output=True, timeout=120)
                    if clip_file.exists():
                        clips.append(clip_file)
                        print(f"  📥 Downloaded: {clip_file.name}")
                except Exception:
                    pass
        except Exception:
            pass
    
    return clips


# ─── Phase 3: Script Generation ──────────────────────────────────────

def generate_script(trend: Trend = None, product_name: str = "",
                    template: str = "curiosity_gap") -> dict:
    """Generate a YouTube Short script with LLM.
    
    Uses Tabassum's winning structure formalized:
    Hook (curiosity gap) → Context → Reveal → Shock ending
    Target: 15-30 seconds spoken (~30-60 words)
    """
    context = ""
    if trend:
        context = f"Trend: {trend.name}\nDescription: {trend.description}\nCuriosity score: {trend.curiosity_score}"
    if product_name:
        context += f"\nProduct to promote: {product_name}"
    
    prompt = f"""Create a YouTube Short script (15-30 seconds, 30-60 words max).

{context}

Template structure (adapt creatively):
1. HOOK (0-3s): Visual impossibility or curiosity gap — "This [subject] tried the [trend] where..."
2. CONTEXT (3-10s): Build tension — "and while most people thought [misdirection]..."
3. REVEAL (10-20s): Show the unexpected — "the last person showed exactly how..."
4. SHOCK END (20-25s): Payoff — "and the result will shock you"

Rules:
- Use conversational American English
- Create an "information gap" that makes viewers NEED to see the end
- Include visual cues in [brackets] for clip editing
- DO NOT add subscribe CTA (Tabassum's insight: no CTA = better retention)
- Maximum 60 words total

Return JSON: {{
  "script": "the full spoken script",
  "word_count": N,
  "estimated_seconds": N,
  "visual_cues": ["cue1", "cue2", ...],
  "hook_text": "the opening hook line",
  "curiosity_score": N (0-100 self-assessment),
  "title_suggestions": ["title1", "title2", "title3"]
}}"""

    result = llm(prompt, system="You are a YouTube Shorts scriptwriter. Return only valid JSON.", max_tokens=800)
    
    try:
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except (json.JSONDecodeError, ValueError):
        pass
    
    # Fallback script
    fallback = {
        "script": "This couple tried the impossible challenge where your legs disappear and while most people thought they figured it out, the last guy showed the real method and it will shock you.",
        "word_count": 30,
        "estimated_seconds": 18,
        "visual_cues": ["couple attempting challenge", "close up on legs", "reveal shot"],
        "hook_text": "This couple tried the impossible challenge",
        "curiosity_score": 65,
        "title_suggestions": ["Trend goes viral 🤯", "How to do the impossible trend", "Wait for the end..."],
    }
    return fallback


# ─── Phase 4: Voiceover (edge-tts, free) ─────────────────────────────

def generate_voiceover(script_text: str, output_path: Path,
                       voice: str = "en-US-GuyNeural",
                       rate: str = "+5%") -> Optional[Path]:
    """Generate voiceover using edge-tts (Microsoft TTS, free).
    
    Voice options:
    - en-US-GuyNeural: American male (Tabassum recommends for higher RPM)
    - en-US-ChristopherNeural: Conversational male
    - en-US-EricNeural: Deep authoritative male
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        import edge_tts
        
        communicate = edge_tts.Communicate(script_text, voice, rate=rate)
        import asyncio
        asyncio.run(communicate.save(str(output_path)))
        
        if output_path.exists() and output_path.stat().st_size > 1000:
            print(f"  🎙️  Voiceover: {output_path.name} ({output_path.stat().st_size // 1024}KB)")
            return output_path
    except ImportError:
        print("  ⚠️  edge-tts not installed. Run: pip install edge-tts")
    except Exception as e:
        print(f"  ⚠️  Voiceover error: {str(e)[:60]}")
    
    return None


# ─── Phase 5: Video Assembly (ffmpeg) ────────────────────────────────

def assemble_short(clips: list[Path], voiceover: Path, script_text: str,
                   output_path: Path, music_path: Path = None,
                   duration_target: float = 25.0) -> Optional[Path]:
    """Assemble a YouTube Short from clips + voiceover using ffmpeg.
    
    Output: 1080x1920 (9:16), 30fps, H.264
    
    Features:
    - Auto-trim clips to match voiceover duration
    - Center crop to 9:16 aspect ratio
    - Subtle zoom effect (Ken Burns-like)
    - Background music (optional, -20dB)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not clips and not voiceover:
        print("  ❌ No clips or voiceover to assemble")
        return None
    
    try:
        # Step 1: Get voiceover duration
        probe = subprocess.run([
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(voiceover)
        ], capture_output=True, text=True, timeout=10)
        vo_duration = float(probe.stdout.strip())
        
        # Step 2: Concatenate clips (if multiple)
        concat_list = output_path.parent / "concat_list.txt"
        with open(concat_list, 'w') as f:
            for clip in clips[:5]:
                f.write(f"file '{clip}'\n")
        
        if len(clips) > 1:
            merged = output_path.parent / "merged_clips.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_list), "-c", "copy", str(merged)
            ], capture_output=True, timeout=60)
        else:
            merged = clips[0]
        
        # Step 3: Build the short
        # - Scale to 1080x1920 (crop center)
        # - Match clip duration to voiceover
        # - Add subtle zoom
        cmd = [
            "ffmpeg", "-y",
            "-i", str(merged),          # video input
            "-i", str(voiceover),       # audio input
            "-t", str(vo_duration + 1),  # duration = voiceover + 1s buffer
            "-filter_complex",
            # Scale to fill 1080x1920, crop excess, subtle zoom
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"zoompan=z='min(zoom+0.001,1.2)':d={int(vo_duration*30)}:s=1080x1920:fps=30[v]",
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            str(output_path)
        ]
        
        # Add background music if provided
        if music_path and music_path.exists():
            cmd = [
                "ffmpeg", "-y",
                "-i", str(merged),
                "-i", str(voiceover),
                "-i", str(music_path),
                "-t", str(vo_duration + 1),
                "-filter_complex",
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                f"zoompan=z='min(zoom+0.001,1.2)':d={int(vo_duration*30)}:s=1080x1920:fps=30[v]"
                f";[1:a][2:a]amix=inputs=2:duration=shortest:weights=1.0 0.1[a]",
                "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                str(output_path)
            ]
        
        subprocess.run(cmd, capture_output=True, timeout=120)
        
        # Cleanup temp files
        concat_list.unlink(missing_ok=True)
        if len(clips) > 1 and merged.exists():
            merged.unlink()
        
        if output_path.exists() and output_path.stat().st_size > 10000:
            size_mb = output_path.stat().st_size / (1024 * 1024)
            print(f"  🎬 Short produced: {output_path.name} ({size_mb:.1f}MB, ~{vo_duration:.0f}s)")
            return output_path
        else:
            print("  ❌ Assembly failed (output too small)")
            
    except Exception as e:
        print(f"  ❌ Assembly error: {str(e)[:80]}")
    
    return None


def generate_subtitles(voiceover_path: Path, output_srt: Path) -> Optional[Path]:
    """Generate SRT subtitles from voiceover using faster-whisper."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(voiceover_path), language="en")
        
        srt_content = []
        for i, seg in enumerate(segments, 1):
            start = _format_srt_time(seg.start)
            end = _format_srt_time(seg.end)
            srt_content.append(f"{i}\n{start} --> {end}\n{seg.text.strip()}\n")
        
        output_srt.write_text("\n".join(srt_content))
        print(f"  📝 Subtitles: {output_srt.name}")
        return output_srt
    except ImportError:
        # Fallback: generate simple word-by-word subtitles
        print("  ⚠️  faster-whisper not available. Skipping subtitles.")
        return None
    except Exception as e:
        print(f"  ⚠️  Subtitle error: {str(e)[:60]}")
        return None


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path) -> Optional[Path]:
    """Burn subtitles into video using ffmpeg."""
    if not srt_path or not srt_path.exists():
        return video_path
    
    try:
        # Escape SRT path for ffmpeg
        srt_escaped = str(srt_path).replace("'", "'\\''")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"subtitles='{srt_escaped}':force_style='FontSize=20,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Alignment=2,MarginV=50'",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "copy",
            str(output_path)
        ], capture_output=True, timeout=120)
        
        if output_path.exists():
            output_path.rename(video_path)  # Replace original
            print(f"  🔥 Subtitles burned into video")
            return video_path
    except Exception as e:
        print(f"  ⚠️  Burn error: {str(e)[:60]}")
    
    return video_path


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ─── Phase 5b: Overlay Generator (Red Arrows, Circles, Glow) ───────

def create_overlay_assets(output_dir: Path) -> dict:
    """Generate PNG overlay assets: red arrow, red circle, glow circle.
    
    Tabassum's insight: "He uses a fast red arrow at the start. Popping subtitles."
    We generate these programmatically with Pillow — no external assets needed.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = {}
    
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # 1. Red Arrow (pointing right, with glow)
        arrow_w, arrow_h = 200, 80
        img = Image.new('RGBA', (arrow_w, arrow_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Glow (semi-transparent red behind)
        glow_points = [(20, 40), (60, 10), (60, 25), (180, 25), (180, 55), (60, 55), (60, 70)]
        draw.polygon(glow_points, fill=(255, 50, 50, 80))
        # Main arrow
        arrow_points = [(25, 40), (55, 15), (55, 28), (175, 28), (175, 52), (55, 52), (55, 65)]
        draw.polygon(arrow_points, fill=(255, 30, 30, 220), outline=(255, 255, 255, 160))
        assets['arrow'] = output_dir / 'arrow_red.png'
        img.save(assets['arrow'])
        
        # 2. Red Circle (with glow border)
        circ_size = 180
        img2 = Image.new('RGBA', (circ_size, circ_size), (0, 0, 0, 0))
        draw2 = ImageDraw.Draw(img2)
        # Outer glow
        for i in range(8, 0, -1):
            alpha = 20 + i * 10
            draw2.ellipse([i, i, circ_size - i, circ_size - i], outline=(255, 50, 50, alpha), width=2)
        # Main circle
        draw2.ellipse([10, 10, circ_size - 10, circ_size - 10], 
                      outline=(255, 30, 30, 240), width=4)
        assets['circle'] = output_dir / 'circle_red.png'
        img2.save(assets['circle'])
        
        # 3. Bounce Circle (thicker, more visible for "pop-in" effect)
        bounce_size = 220
        img3 = Image.new('RGBA', (bounce_size, bounce_size), (0, 0, 0, 0))
        draw3 = ImageDraw.Draw(img3)
        for i in range(12, 0, -1):
            alpha = 15 + i * 8
            draw3.ellipse([i, i, bounce_size - i, bounce_size - i], 
                         outline=(255, 80, 80, alpha), width=3)
        draw3.ellipse([8, 8, bounce_size - 8, bounce_size - 8], 
                      outline=(255, 20, 20, 250), width=5)
        assets['bounce_circle'] = output_dir / 'bounce_circle.png'
        img3.save(assets['bounce_circle'])
        
        # 4. Yellow highlight flash (for text emphasis)
        flash_w, flash_h = 300, 60
        img4 = Image.new('RGBA', (flash_w, flash_h), (0, 0, 0, 0))
        draw4 = ImageDraw.Draw(img4)
        draw4.rounded_rectangle([0, 0, flash_w, flash_h], radius=10, 
                                fill=(255, 255, 0, 100))
        assets['highlight'] = output_dir / 'highlight_yellow.png'
        img4.save(assets['highlight'])
        
        print(f"  🎨 Overlay assets generated: {len(assets)} files")
        
    except ImportError:
        print("  ⚠️  Pillow not available. Skipping overlay generation.")
    
    return assets


def apply_overlays(video_path: Path, overlays: dict, srt_path: Path = None,
                   output_path: Path = None, timestamps: list[dict] = None) -> Optional[Path]:
    """Apply overlay animations (arrows, circles) to video via ffmpeg.
    
    timestamps format: [{"type": "arrow", "start": 0.0, "duration": 3.0, "x": 800, "y": 400}, ...]
    If no timestamps given, auto-generates from script structure.
    """
    if not output_path:
        output_path = video_path.parent / (video_path.stem + '_overlaid.mp4')
    
    if not timestamps:
        # Auto-generate: arrow at 0-3s, circle at 8-12s, bounce at 15-18s
        timestamps = [
            {"type": "arrow", "start": 0.5, "duration": 2.5, "x": 750, "y": 350},
            {"type": "circle", "start": 8.0, "duration": 3.0, "x": 540, "y": 800},
            {"type": "bounce_circle", "start": 15.0, "duration": 3.0, "x": 540, "y": 600},
        ]
    
    if not timestamps or not overlays:
        return video_path
    
    # Build ffmpeg overlay filter chain
    filter_parts = []
    input_idx = 1  # 0 is main video
    overlay_inputs = []
    
    for ts in timestamps:
        overlay_type = ts.get("type", "arrow")
        overlay_file = overlays.get(overlay_type)
        if not overlay_file or not overlay_file.exists():
            continue
        
        overlay_inputs.append(str(overlay_file))
        start = ts.get("start", 0)
        dur = ts.get("duration", 3)
        x = ts.get("x", 540)
        y = ts.get("y", 800)
        
        # Pop-in effect: scale from 0 to 1 in first 0.2s
        enable_expr = f"between(t,{start},{start + dur})"
        
        if len(filter_parts) == 0:
            # First overlay on main video
            filter_parts.append(
                f"[{input_idx}:v]scale={180 if 'circle' in overlay_type else 150}:-1[ov{input_idx}];"
                f"[0:v][ov{input_idx}]overlay=x={x}:y={y}:enable='{enable_expr}':format=auto[v{input_idx}]"
            )
        else:
            # Subsequent overlays on previous result
            prev = input_idx - 1
            filter_parts.append(
                f"[{input_idx}:v]scale={180 if 'circle' in overlay_type else 150}:-1[ov{input_idx}];"
                f"[v{prev}][ov{input_idx}]overlay=x={x}:y={y}:enable='{enable_expr}':format=auto[v{input_idx}]"
            )
        input_idx += 1
    
    if not filter_parts:
        return video_path
    
    # Build ffmpeg command
    last_label = f"v{input_idx - 1}"
    cmd = ["ffmpeg", "-y", "-i", str(video_path)]
    for inp in overlay_inputs:
        cmd.extend(["-i", inp])
    
    filter_complex = ";".join(filter_parts)
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", f"[{last_label}]",
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        str(output_path)
    ])
    
    try:
        subprocess.run(cmd, capture_output=True, timeout=120)
        if output_path.exists() and output_path.stat().st_size > 10000:
            print(f"  🎯 Overlays applied: {output_path.name}")
            return output_path
    except Exception as e:
        print(f"  ⚠️  Overlay error: {str(e)[:60]}")
    
    return video_path


# ─── Phase 5c: Background Music (Beat-Synced) ───────────────────────

def find_trending_music(niche: str = "") -> list[dict]:
    """Find trending audio tracks for YouTube Shorts.
    
    Strategy: Use YouTube's own trending audio library.
    Falls back to known viral tracks.
    """
    # Known viral TikTok/Shorts audio tracks (constantly updated)
    VIRAL_TRACKS = [
        {"name": "Not Cute Anymore - Illit", "bpm": 130, "energy": "high", "mood": "trendy"},
        {"name": "Paint The Town Red - Doja Cat", "bpm": 95, "energy": "high", "mood": "bold"},
        {"name": "Greedy - Tate McRae", "bpm": 120, "energy": "medium", "mood": "catchy"},
        {"name": "Water - Tyla", "bpm": 110, "energy": "high", "mood": "dance"},
        {"name": "Snooze - SZA", "bpm": 90, "energy": "low", "mood": "chill"},
        {"name": "Carnival - Kanye West", "bpm": 140, "energy": "high", "mood": "intense"},
    ]
    
    # Try to get more via LLM
    extra = llm(
        f"Name 5 currently trending TikTok/YouTube Shorts audio tracks for the niche '{niche or 'general'}'. "
        f"Return JSON array with: name, bpm (number), energy (low/medium/high), mood",
        system="Return only valid JSON array.",
        max_tokens=400
    )
    
    try:
        match = re.search(r'\[.*\]', extra, re.DOTALL)
        if match:
            viral = json.loads(match.group())
            VIRAL_TRACKS.extend(viral)
    except:
        pass
    
    return VIRAL_TRACKS


def download_music(track_name: str, output_dir: Path) -> Optional[Path]:
    """Download a music track using yt-dlp (YouTube Music search)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', track_name)[:40]
    output_file = output_dir / f"music_{safe_name}.mp3"
    
    if output_file.exists():
        return output_file
    
    try:
        subprocess.run([
            "yt-dlp", "-x", "--audio-format", "mp3",
            "--max-filesize", "10M",
            f"ytsearch1:{track_name} audio",
            "-o", str(output_file.with_suffix('')),  # yt-dlp adds .mp3
        ], capture_output=True, timeout=60)
        
        # yt-dlp might save as .mp3 or .webm
        for ext in ['.mp3', '.webm', '.m4a', '.opus']:
            candidate = output_file.with_suffix(ext)
            if candidate.exists():
                if ext != '.mp3':
                    # Convert to mp3
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(candidate),
                        "-c:a", "libmp3lame", "-q:a", "5",
                        str(output_file)
                    ], capture_output=True, timeout=30)
                    candidate.unlink()
                if output_file.exists():
                    print(f"  🎵 Downloaded: {track_name} ({output_file.stat().st_size // 1024}KB)")
                    return output_file
    except Exception as e:
        print(f"  ⚠️  Music download error: {str(e)[:60]}")
    
    return None


def mix_audio(voiceover_path: Path, music_path: Path, output_path: Path,
              voice_vol: float = 1.0, music_vol: float = 0.08,
              beat_drop_time: float = 0.0) -> Optional[Path]:
    """Mix voiceover + background music with beat-drop sync.
    
    Uses pydub for precise control:
    - Music starts quiet (-20dB relative)
    - Volume rises at beat_drop_time
    - Voiceover always on top
    
    Falls back to ffmpeg if pydub unavailable.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        from pydub import AudioSegment
        
        voice = AudioSegment.from_file(str(voiceover_path))
        music = AudioSegment.from_file(str(music_path))
        
        # Trim/pad music to voice length
        if len(music) > len(voice):
            music = music[:len(voice) + 2000]  # 2s extra
        elif len(music) < len(voice):
            # Loop music
            loops_needed = (len(voice) // len(music)) + 1
            music = music * loops_needed
            music = music[:len(voice) + 2000]
        
        # Apply music volume (quiet baseline)
        music_quiet = music - (20 - int(music_vol * 100))  # dB reduction
        
        # Beat drop: raise volume at beat_drop_time
        if beat_drop_time > 0:
            drop_ms = int(beat_drop_time * 1000)
            if drop_ms < len(voice):
                before_drop = music_quiet[:drop_ms]
                after_drop = music_quiet[drop_ms:] + 8  # Louder after drop
                music_quiet = before_drop + after_drop
        
        # Mix
        mixed = voice.overlay(music_quiet)
        mixed.export(str(output_path), format='mp3')
        
        if output_path.exists():
            print(f"  🎛️  Audio mixed: voice + music → {output_path.name}")
            return output_path
            
    except ImportError:
        # Fallback: ffmpeg amix
        cmd = [
            "ffmpeg", "-y",
            "-i", str(voiceover_path),
            "-i", str(music_path),
            "-filter_complex",
            f"[0:a]volume={voice_vol}[v];[1:a]volume={music_vol},adelay=0|0[m];[v][m]amix=inputs=2:duration=shortest[a]",
            "-map", "[a]", "-c:a", "libmp3lame", "-q:a", "5",
            str(output_path)
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=30)
            if output_path.exists():
                print(f"  🎛️  Audio mixed (ffmpeg): {output_path.name}")
                return output_path
        except:
            pass
    except Exception as e:
        print(f"  ⚠️  Mix error: {str(e)[:60]}")
    
    return None


# ─── Phase 5d: Smart Clip Finder (Better Source Material) ────────────

def smart_clip_search(query: str, max_clips: int = 5, 
                      min_views: int = 10000,
                      platforms: list[str] = None) -> list[dict]:
    """Intelligent clip search across multiple platforms.
    
    Strategies:
    1. YouTube Shorts (sorted by views)
    2. TikTok via yt-dlp
    3. Direct URL from trend data
    
    Filters:
    - Duration < 60s
    - Views > min_views
    - Deduplication by title similarity
    """
    platforms = platforms or ["youtube", "tiktok"]
    results = []
    seen_titles = set()
    
    for platform in platforms:
        if platform == "youtube":
            search_url = f"ytsearch{max_clips * 2}:{query} short"
            try:
                cmd = ["yt-dlp", "--flat-playlist", "-j", search_url,
                       "--playlist-end", str(max_clips * 2)]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                for line in r.stdout.strip().split('\n'):
                    if not line.strip(): continue
                    try:
                        v = json.loads(line)
                        views = v.get('view_count', 0) or 0
                        dur = v.get('duration', 999) or 999
                        title = v.get('title', '')
                        
                        # Dedup
                        title_key = re.sub(r'[^a-zA-Z0-9]', '', title.lower())[:30]
                        if title_key in seen_titles:
                            continue
                        seen_titles.add(title_key)
                        
                        if dur < 60 and views >= min_views:
                            results.append({
                                'title': title,
                                'url': v.get('webpage_url', ''),
                                'views': views,
                                'duration': dur,
                                'platform': 'youtube',
                                'uploader': v.get('uploader', ''),
                            })
                    except json.JSONDecodeError:
                        continue
            except Exception:
                pass
        
        elif platform == "tiktok":
            # TikTok via yt-dlp (limited but works for public videos)
            try:
                search_url = f"ttsearch:{query}"
                cmd = ["yt-dlp", "--flat-playlist", "-j", search_url,
                       "--playlist-end", str(max_clips)]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                for line in r.stdout.strip().split('\n'):
                    if not line.strip(): continue
                    try:
                        v = json.loads(line)
                        dur = v.get('duration', 999) or 999
                        if dur < 60:
                            title_key = re.sub(r'[^a-zA-Z0-9]', '', v.get('title', '').lower())[:30]
                            if title_key in seen_titles:
                                continue
                            seen_titles.add(title_key)
                            results.append({
                                'title': v.get('title', ''),
                                'url': v.get('webpage_url', ''),
                                'views': v.get('view_count', 0) or 0,
                                'duration': dur,
                                'platform': 'tiktok',
                                'uploader': v.get('uploader', ''),
                            })
                    except:
                        continue
            except:
                pass
    
    # Sort by views
    results.sort(key=lambda x: x['views'], reverse=True)
    return results[:max_clips]


def download_best_clips(query: str, output_dir: Path, max_clips: int = 3,
                        min_views: int = 5000) -> list[Path]:
    """Smart clip download: search → filter → download best quality."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find clips
    clips_info = smart_clip_search(query, max_clips=max_clips * 2, min_views=min_views)
    
    if not clips_info:
        # Fallback: lower threshold
        clips_info = smart_clip_search(query, max_clips=max_clips * 2, min_views=0)
    
    if not clips_info:
        print(f"  ⚠️  No clips found for: {query}")
        return []
    
    print(f"  Found {len(clips_info)} clips, downloading top {max_clips}...")
    
    downloaded = []
    for i, clip in enumerate(clips_info[:max_clips]):
        clip_file = output_dir / f"clip_{i:03d}.mp4"
        if clip_file.exists():
            downloaded.append(clip_file)
            continue
        
        try:
            subprocess.run([
                "yt-dlp", "-f", "best[height<=720]", 
                "--max-filesize", "50M",
                "-o", str(clip_file),
                clip['url']
            ], capture_output=True, timeout=120)
            
            if clip_file.exists() and clip_file.stat().st_size > 5000:
                downloaded.append(clip_file)
                print(f"  📥 [{clip['views']:,} views] {clip['title'][:40]}")
            else:
                # Try lower quality
                subprocess.run([
                    "yt-dlp", "-f", "worst",
                    "--max-filesize", "30M",
                    "-o", str(clip_file),
                    clip['url']
                ], capture_output=True, timeout=60)
                if clip_file.exists() and clip_file.stat().st_size > 5000:
                    downloaded.append(clip_file)
        except Exception:
            pass
    
    return downloaded


# ─── Phase 6: YouTube Upload (OAuth) ─────────────────────────────────

# YouTube API scopes
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# Client secrets file (user must obtain from Google Cloud Console)
CLIENT_SECRETS_FILE = BASE_DIR / "state" / "youtube_client_secret.json"
CREDENTIALS_FILE = BASE_DIR / "state" / "youtube_credentials.json"


def get_youtube_auth_url() -> str:
    """Generate OAuth authorization URL for YouTube API.
    
    User must:
    1. Go to console.cloud.google.com
    2. Create project → Enable YouTube Data API v3
    3. Create OAuth 2.0 credentials → Download JSON
    4. Save as agents/state/youtube_client_secret.json
    """
    if not CLIENT_SECRETS_FILE.exists():
        return ""
    
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRETS_FILE), scopes=YOUTUBE_SCOPES)
        auth_url, _ = flow.authorization_url(prompt='consent')
        return auth_url
    except Exception as e:
        print(f"  ⚠️  OAuth error: {str(e)[:60]}")
        return ""


def get_youtube_service():
    """Get authenticated YouTube service. Returns None if not authenticated."""
    if not CREDENTIALS_FILE.exists():
        return None
    
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        
        creds = Credentials.from_authorized_user_file(str(CREDENTIALS_FILE), YOUTUBE_SCOPES)
        
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            CREDENTIALS_FILE.write_text(creds.to_json())
        
        if creds and creds.valid:
            return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=creds)
    except Exception as e:
        print(f"  ⚠️  Auth error: {str(e)[:60]}")
    
    return None


def authenticate_youtube(headless: bool = True) -> bool:
    """Run OAuth flow for YouTube API.
    
    If headless: prints URL for user to visit manually.
    If not headless: opens browser (for local dev).
    """
    if not CLIENT_SECRETS_FILE.exists():
        print("\n❌ YouTube client secret not found.")
        print("  Setup steps:")
        print("  1. Go to: https://console.cloud.google.com")
        print("  2. Create project → Enable 'YouTube Data API v3'")
        print("  3. Create OAuth 2.0 Client ID (Desktop app)")
        print("  4. Download JSON → save as:")
        print(f"     {CLIENT_SECRETS_FILE}")
        return False
    
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRETS_FILE), scopes=YOUTUBE_SCOPES)
        
        if headless:
            # Run manual flow
            flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
            auth_url, _ = flow.authorization_url(prompt='consent')
            
            print(f"\n🔐 Visit this URL to authorize:")
            print(f"{auth_url}\n")
            code = input("Enter the authorization code: ").strip()
            
            flow.fetch_token(code=code)
        else:
            creds = flow.run_local_server(port=0)
        
        # Save credentials
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CREDENTIALS_FILE.write_text(flow.credentials.to_json())
        print("✅ YouTube API authenticated!")
        return True
        
    except Exception as e:
        print(f"❌ Authentication failed: {str(e)[:80]}")
        return False


def upload_to_youtube(video_path: Path, title: str, description: str = "",
                      tags: list[str] = None, privacy: str = "public",
                      thumbnail_path: Path = None) -> Optional[str]:
    """Upload a video to YouTube via API.
    
    Returns the video URL if successful.
    Falls back to manual instructions if not authenticated.
    """
    if not video_path.exists():
        print(f"  ❌ Video file not found: {video_path}")
        return None
    
    service = get_youtube_service()
    
    if not service:
        print("\n  ⚠️  YouTube API not authenticated. Manual upload required:")
        print(f"  1. Go to: https://studio.youtube.com")
        print(f"  2. Click CREATE → Upload videos")
        print(f"  3. Select: {video_path}")
        print(f"  4. Title: {title}")
        print(f"  5. Description: {description[:200]}")
        print(f"  6. Tags: {', '.join(tags or [])}")
        print(f"  7. Set Public → Publish")
        print(f"\n  To enable auto-upload, run: python3 shorts_machine.py --mode auth")
        return None
    
    try:
        import googleapiclient.http as http
        
        body = {
            'snippet': {
                'title': title[:100],
                'description': description[:5000],
                'tags': (tags or [])[:500],
                'categoryId': '24',  # Entertainment
            },
            'status': {
                'privacyStatus': privacy,
                'selfDeclaredMadeForKids': False,
                'embeddable': True,
                'publicStatsViewable': True,
            },
        }
        
        media = http.MediaFileUpload(
            str(video_path), mimetype='video/mp4',
            resumable=True, chunksize=10 * 1024 * 1024  # 10MB chunks
        )
        
        request = service.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media,
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"  📤 Upload: {int(status.progress() * 100)}%")
        
        video_id = response.get('id', '')
        video_url = f"https://youtube.com/shorts/{video_id}"
        print(f"  ✅ Uploaded: {video_url}")
        
        # Upload thumbnail if provided
        if thumbnail_path and thumbnail_path.exists() and video_id:
            try:
                service.thumbnails().set(
                    videoId=video_id,
                    media_body=http.MediaFileUpload(str(thumbnail_path))
                ).execute()
                print(f"  🖼️  Thumbnail set")
            except:
                pass  # Thumbnail upload requires channel verification
        
        return video_url
        
    except Exception as e:
        print(f"  ❌ Upload error: {str(e)[:80]}")
        return None


def prepare_upload(video: ShortVideo, title_idx: int = 0, auto_upload: bool = False) -> dict:
    """Prepare upload metadata and optionally upload to YouTube."""
    title = f"Trend goes viral 🤯"
    
    # Generate title from script if available
    script_data = {}
    if video.script:
        try:
            script_data = json.loads(video.script) if isinstance(video.script, str) else {}
        except:
            pass
    
    titles = script_data.get("title_suggestions", ["Trend goes viral 🤯"])
    title = titles[title_idx % len(titles)]
    
    tags = ["shorts", "trending", "viral", "2026"]
    if video.trend_name:
        tags.append(video.trend_name[:30].replace(" ", ""))
    
    description = f"{title}\n\n#shorts #trending #viral"
    if video.product_link:
        description += f"\n\nGet yours: {video.product_link}"
    
    metadata = {
        "title": title,
        "description": description,
        "tags": tags,
        "category": " Entertainment",
        "privacy": "public",
        "video_path": video.video_path,
        "thumbnail_path": video.thumbnail_path,
        "upload_instructions": (
            "Upload manually to YouTube Studio:\n"
            "1. Go to studio.youtube.com\n"
            "2. Click CREATE → Upload videos\n"
            "3. Select the video file\n"
            f"4. Title: {title}\n"
            f"5. Description: {description}\n"
            "6. Audience: Not made for kids\n"
            "7. Visibility: Public\n"
            "8. Click Publish"
        ),
    }
    
    print(f"\n📤 Upload prepared:")
    print(f"  Title: {title}")
    print(f"  Tags: {', '.join(tags)}")
    print(f"  File: {video.video_path}")
    
    # Try auto-upload if requested
    if auto_upload and video.video_path:
        vp = Path(video.video_path)
        if vp.exists():
            url = upload_to_youtube(vp, title, description, tags, privacy="public",
                                   thumbnail_path=Path(video.thumbnail_path) if video.thumbnail_path else None)
            if url:
                metadata['uploaded_url'] = url
    
    return metadata


# ─── Phase 7: Analysis ───────────────────────────────────────────────

def analyze_performance() -> dict:
    """Analyze performance of posted shorts.
    
    Returns aggregate stats and recommendations.
    """
    channels = _load_channels()
    trends = load_trends()
    
    report = {
        "channels": len(channels),
        "total_videos": sum(c.videos_posted for c in channels),
        "total_views": sum(c.total_views for c in channels),
        "trends_detected": len(trends),
        "avg_curiosity_score": sum(t.curiosity_score for t in trends) / max(len(trends), 1),
        "top_trends": [{"name": t.name[:50], "score": t.curiosity_score, "potential": round(t.viral_potential, 3)} for t in trends[:5]],
        "recommendations": [],
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # Generate recommendations via LLM
    if trends:
        rec_prompt = f"""Based on these detected YouTube Shorts trends, give 3 actionable recommendations:
        
Top trends (curiosity score / viral potential):
{chr(10).join(f"- {t.name[:50]} ({t.curiosity_score}/100, potential: {t.viral_potential:.3f})" for t in trends[:5])}

Focus on: which trend to produce first, what spin to add, and optimal posting time."""
        
        recs = llm(rec_prompt, system="You are a YouTube Shorts strategist. Be concise.", max_tokens=300)
        if recs:
            report["recommendations"] = recs.split('\n')
    
    return report


# ─── Channel Management ──────────────────────────────────────────────

def _load_channels() -> list[Channel]:
    if not CHANNELS_FILE.exists():
        return []
    data = json.loads(CHANNELS_FILE.read_text())
    return [Channel(**d) for d in data]


def _save_channels(channels: list[Channel]):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = [asdict(c) for c in channels]
    CHANNELS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def create_channel(name: str, handle: str, niche: str) -> Channel:
    """Register a new YouTube Shorts channel."""
    ch = Channel(
        name=name, handle=handle, niche=niche,
        status="warmup",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    channels = _load_channels()
    channels.append(ch)
    _save_channels(channels)
    print(f"✅ Channel registered: {name} (@{handle}) — niche: {niche}")
    return ch


# ─── Journal ─────────────────────────────────────────────────────────

def _journal(action: str, details: dict):
    """Write to WORM journal."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": "shorts_machine",
        "action": action,
        **details,
    }
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{action}.json"
    (JOURNAL_DIR / filename).write_text(json.dumps(entry, indent=2, ensure_ascii=False))


# ─── Main Pipeline ───────────────────────────────────────────────────

def run_trend_detection(niche: str = "", max_trends: int = 10) -> list[Trend]:
    """Run trend detection pipeline."""
    print("=" * 60)
    print("📺 SHORTS MACHINE — Trend Detection")
    print("=" * 60)
    
    trends = detect_trends(niche=niche, max_trends=max_trends)
    
    if not trends:
        print("\n⚠️  No trends detected. Try a different niche or check connectivity.")
    else:
        print(f"\n✅ {len(trends)} trends detected. Top pick:")
        best = trends[0]
        print(f"   {best.name[:70]}")
        print(f"   Curiosity: {best.curiosity_score}/100 | Potential: {best.viral_potential:.3f}")
    
    _journal("trend_detection", {"niche": niche, "trends_found": len(trends)})
    return trends


def run_produce(trend_name: str = "", product_name: str = "",
                template: str = "", channel_name: str = "") -> Optional[ShortVideo]:
    """Run the production pipeline for a single short."""
    print("=" * 60)
    print("🎬 SHORTS MACHINE — Production Pipeline")
    print("=" * 60)
    
    # Load or detect trend
    trend = None
    if trend_name:
        trends = load_trends()
        matches = [t for t in trends if trend_name.lower() in t.name.lower()]
        trend = matches[0] if matches else None
    
    if not trend and product_name:
        # Product-focused: create a trend from product
        trend = Trend(name=f"{product_name} product demo", niche="product",
                      curiosity_score=score_curiosity(product_name))
    
    if not trend:
        # Auto-detect
        trends = detect_trends(max_trends=3)
        trend = trends[0] if trends else None
    
    if not trend:
        print("❌ No trend to produce. Run --mode trend first.")
        return None
    
    print(f"\n🎯 Producing short for: {trend.name[:60]}")
    print(f"   Curiosity: {trend.curiosity_score}/100")
    
    # Step 1: Generate script
    print("\n  Step 1/8: Generating script...")
    script_data = generate_script(trend=trend, product_name=product_name, template=template)
    script_text = script_data.get("script", "")
    print(f"    Script: {script_text[:80]}...")
    print(f"    Words: {script_data.get('word_count', '?')} | Duration: ~{script_data.get('estimated_seconds', '?')}s")
    
    # Step 2: Generate voiceover
    print("\n  Step 2/8: Generating voiceover...")
    video_id = hashlib.md5(f"{trend.name}{time.time()}".encode()).hexdigest()[:8]
    work_dir = SHORTS_DIR / video_id
    vo_path = work_dir / "voiceover.mp3"
    vo_result = generate_voiceover(script_text, vo_path)
    
    if not vo_result:
        print("  ❌ Voiceover failed. Cannot produce short.")
        return None
    
    # Step 3: Smart clip search & download
    print("\n  Step 3/8: Finding source clips (smart search)...")
    clips_dir = work_dir / "clips"
    search_query = trend.name[:40] if trend.name else product_name
    clips = download_best_clips(search_query, clips_dir, max_clips=3, min_views=1000)
    if not clips:
        clips = download_clips(trend, clips_dir, max_clips=3)
    print(f"    Downloaded: {len(clips)} clips")
    
    # Step 4: Background music
    mixed_audio = vo_result
    if use_music:
        print("\n  Step 4/8: Finding background music...")
        tracks = find_trending_music(trend.niche)
        if tracks:
            track = tracks[0]
            music_file = download_music(track['name'], work_dir / "music")
            if music_file:
                mixed_path = work_dir / "audio_mixed.mp3"
                mixed = mix_audio(vo_result, music_file, mixed_path,
                                  voice_vol=1.0, music_vol=0.08,
                                  beat_drop_time=float(script_data.get('estimated_seconds', 15)) * 0.7)
                if mixed:
                    mixed_audio = mixed
            else:
                print("    ⚠️  Music download failed, using voiceover only")
    else:
        print("\n  Step 4/8: Music skipped")
    
    # Step 5: Assemble video
    print("\n  Step 5/8: Assembling video...")
    video_path = work_dir / f"short_{video_id}.mp4"
    assembled = assemble_short(clips, mixed_audio, script_text, video_path)
    
    # Step 6: Subtitles
    print("\n  Step 6/8: Adding subtitles...")
    srt_path = work_dir / "subtitles.srt"
    srt = generate_subtitles(vo_result, srt_path)
    if srt and assembled:
        burn_subtitles(assembled, srt, work_dir / "short_subtitled.mp4")
    
    # Step 7: Overlays
    final_video = assembled
    if use_overlays and assembled:
        print("\n  Step 7/8: Applying overlays...")
        assets = create_overlay_assets(work_dir / "overlays")
        if assets:
            final_video = apply_overlays(
                assembled, assets, srt,
                output_path=work_dir / f"short_{video_id}_final.mp4"
            )
    else:
        print("\n  Step 7/8: Overlays skipped")
    
    # Step 8: Upload
    print("\n  Step 8/8: Preparing upload...")
    
    # Create video record
    video = ShortVideo(
        id=video_id,
        trend_name=trend.name[:60],
        channel=channel_name,
        script=json.dumps(script_data),
        audio_path=str(vo_result),
        video_path=str(final_video) if final_video else "",
        duration_sec=script_data.get("estimated_seconds", 0),
        curiosity_score=script_data.get("curiosity_score", trend.curiosity_score),
        template_used=template or "curiosity_gap",
        product_name=product_name,
        status="produced" if final_video else "failed",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    # Save & upload
    video_file = work_dir / "video.json"
    video_file.parent.mkdir(parents=True, exist_ok=True)
    video_file.write_text(json.dumps(asdict(video), indent=2, ensure_ascii=False))
    
    if final_video:
        upload = prepare_upload(video, auto_upload=auto_upload)
        upload_file = work_dir / "upload_metadata.json"
        upload_file.write_text(json.dumps(upload, indent=2, ensure_ascii=False))
    
    _journal("produce_short", {"video_id": video_id, "trend": trend.name[:50], "status": video.status})
    
    print(f"\n{'✅' if final_video else '❌'} Short {video_id}: {video.status}")
    if final_video:
        print(f"   File: {final_video}")
        print(f"   Upload: {work_dir / 'upload_metadata.json'}")
    
    return video


def run_batch(count: int = 5, niche: str = "") -> list[ShortVideo]:
    """Batch produce multiple shorts."""
    print("=" * 60)
    print(f"🏭 SHORTS MACHINE — Batch Production ({count} shorts)")
    print("=" * 60)
    
    # Detect trends first
    trends = detect_trends(niche=niche, max_trends=count)
    
    if not trends:
        print("❌ No trends detected for batch production.")
        return []
    
    videos = []
    for i, trend in enumerate(trends[:count]):
        print(f"\n--- Short {i+1}/{min(len(trends), count)} ---")
        video = run_produce(trend_name=trend.name)
        if video:
            videos.append(video)
        time.sleep(2)  # Rate limit between productions
    
    print(f"\n{'='*60}")
    print(f"✅ Batch complete: {len(videos)}/{count} shorts produced")
    
    _journal("batch_produce", {"requested": count, "produced": len(videos)})
    return videos


def run_full_pipeline(niche: str = "", product_name: str = "") -> Optional[ShortVideo]:
    """Full pipeline: trend detection → production in one go."""
    print("=" * 60)
    print("🚀 SHORTS MACHINE — Full Pipeline")
    print("=" * 60)
    
    # Detect trends
    trends = detect_trends(niche=niche, max_trends=5)
    
    if not trends:
        print("❌ No trends found.")
        return None
    
    # Pick best trend
    best = trends[0]
    print(f"\n🏆 Best trend: {best.name[:60]} (curiosity: {best.curiosity_score}/100)")
    
    # Produce
    video = run_produce(trend_name=best.name, product_name=product_name)
    
    _journal("full_pipeline", {"trend": best.name[:50], "video_id": video.id if video else "failed"})
    return video


def run_analysis():
    """Run performance analysis."""
    print("=" * 60)
    print("📊 SHORTS MACHINE — Performance Analysis")
    print("=" * 60)
    
    report = analyze_performance()
    
    print(f"\n  Channels: {report['channels']}")
    print(f"  Total videos: {report['total_videos']}")
    print(f"  Total views: {report['total_views']:,}")
    print(f"  Trends detected: {report['trends_detected']}")
    print(f"  Avg curiosity score: {report['avg_curiosity_score']:.1f}/100")
    
    if report['top_trends']:
        print(f"\n  Top trends:")
        for t in report['top_trends']:
            print(f"    - {t['name']} ({t['score']}/100, potential: {t['potential']})")
    
    if report['recommendations']:
        print(f"\n  Recommendations:")
        for r in report['recommendations']:
            if r.strip():
                print(f"    {r.strip()}")


# ─── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SHORTS MACHINE — YouTube Shorts Automation for DropAtom",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 shorts_machine.py --mode trend                       # Detect trends
  python3 shorts_machine.py --mode trend --niche "beauty"      # Niche trends
  python3 shorts_machine.py --mode produce                     # Produce from best trend
  python3 shorts_machine.py --mode produce --trend "owl"       # Specific trend
  python3 shorts_machine.py --mode produce --product "Brush"   # Product-focused
  python3 shorts_machine.py --mode batch --count 5             # Batch 5 shorts
  python3 shorts_machine.py --mode full                        # Full pipeline
  python3 shorts_machine.py --mode analyze                     # Analyze performance
  python3 shorts_machine.py --mode channel --name "Vibe Steps" --handle "vibesteps" --niche "dance"
  python3 shorts_machine.py --mode auth                          # YouTube OAuth setup
  python3 shorts_machine.py --mode produce --upload              # Auto-upload after produce
  python3 shorts_machine.py --mode produce --no-music            # Skip background music
  python3 shorts_machine.py --mode produce --no-overlays         # Skip overlay animations
        """
    )
    
    parser.add_argument("--mode", choices=["trend", "produce", "batch", "full", "analyze", "channel", "auth"],
                        default="trend", help="Operation mode")
    parser.add_argument("--niche", default="", help="Target niche")
    parser.add_argument("--trend", default="", help="Trend name to produce")
    parser.add_argument("--product", default="", help="Product name for product-focused shorts")
    parser.add_argument("--template", default="", choices=list(SCRIPT_TEMPLATES.keys()),
                        help="Script template")
    parser.add_argument("--count", type=int, default=5, help="Number of shorts for batch mode")
    parser.add_argument("--channel", default="", help="Channel name for posting")
    parser.add_argument("--upload", action="store_true", help="Auto-upload to YouTube")
    parser.add_argument("--no-music", action="store_true", help="Skip background music")
    parser.add_argument("--no-overlays", action="store_true", help="Skip overlay animations")
    
    # Channel management
    parser.add_argument("--name", default="", help="Channel name (for --mode channel)")
    parser.add_argument("--handle", default="", help="Channel handle (for --mode channel)")
    
    args = parser.parse_args()
    
    if args.mode == "trend":
        run_trend_detection(niche=args.niche)
    elif args.mode == "produce":
        run_produce(trend_name=args.trend, product_name=args.product,
                    template=args.template, channel_name=args.channel,
                    auto_upload=args.upload,
                    use_music=not args.no_music,
                    use_overlays=not args.no_overlays)
    elif args.mode == "batch":
        run_batch(count=args.count, niche=args.niche)
    elif args.mode == "full":
        run_full_pipeline(niche=args.niche, product_name=args.product)
    elif args.mode == "analyze":
        run_analysis()
    elif args.mode == "channel":
        if not args.name or not args.handle:
            print("❌ --name and --handle required for channel creation")
            sys.exit(1)
        create_channel(args.name, args.handle, args.niche or "general")
    elif args.mode == "auth":
        authenticate_youtube()


if __name__ == "__main__":
    main()
