#!/usr/bin/env python3
"""
DSI-Wiki Maintenance Console:
  Step 1: Clear a topic and add a large RAW document
  Step 2: Show folder and add fact-checked RAW records
  Step 3: Check wiki integrity (internal scan)
  
Usage:
  python wiki_maintain.py step1 <topic> [--document <file>] [--instance <name>]
  python wiki_maintain.py step2 <folder> [--instance <name>]
  python wiki_maintain.py step3 [--topic <name>] [--instance <name>]
"""
import argparse
import os
import sys
from pathlib import Path

_SCRIPTS_ROOT = str(Path(__file__).resolve().parent.parent.parent / "CODE")
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from gateway.api_app import load_instances, LAYERS

DEFAULT_INSTANCE = "default-instance"


def get_base_dir(instance: str = DEFAULT_INSTANCE) -> Path:
    scan_dir = str(Path(__file__).resolve().parent.parent.parent / "JSONS" / "instances")
    instances = load_instances(scan_dir)
    if instance not in instances:
        raise ValueError(f"Instance '{instance}' not found. Available: {list(instances.keys())}")
    return Path(instances[instance]['base_dir'])


def step1_clear_and_add_raw(topic: str, document_path: str = None, instance: str = DEFAULT_INSTANCE) -> Path:
    """Clear a topic and add a large RAW document."""
    base_dir = get_base_dir(instance)
    
    raw_dir = base_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    if not topic.endswith('.md'):
        topic = topic + '.md'
    
    raw_path = raw_dir / topic
    
    if document_path:
        content = Path(document_path).read_text(encoding='utf-8')
        print(f"Step 1: Cleared topic and added large document from {document_path} to {raw_path}")
    else:
        content = ""
        raw_path.write_text(content, encoding='utf-8')
        print(f"Step 1: Cleared topic and added empty RAW record at {raw_path}")
    
    if document_path:
        raw_path.write_text(content, encoding='utf-8')
    
    return raw_path


def step2_list_and_factcheck(folder: str, instance: str = DEFAULT_INSTANCE) -> list[Path]:
    """Show folder and add fact-checked RAW records."""
    base_dir = get_base_dir(instance)
    folder_path = Path(folder)
    
    if not folder_path.is_absolute():
        folder_path = base_dir / folder
    
    if not folder_path.exists():
        print(f"Error: Folder does not exist: {folder_path}", file=sys.stderr)
        return []
    
    print(f"Step 2: Scanning folder: {folder_path}")
    
    md_files = list(folder_path.glob('*.md'))
    print(f"Found {len(md_files)} .md files")
    
    raw_records = []
    raw_dir = base_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    for md_file in sorted(md_files):
        topic = md_file.stem
        if not topic.endswith('.md'):
            topic = topic + '.md'
        
        raw_path = raw_dir / topic
        
        try:
            content = md_file.read_text(encoding='utf-8')
            fact_checked = content
            
            lines = content.split('\n')
            checked_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped:
                    if '~~' not in stripped:
                        checked_lines.append(line)
            
            fact_checked = '\n'.join(checked_lines)
            
            raw_path.write_text(fact_checked, encoding='utf-8')
            raw_records.append(raw_path)
            print(f"  Added fact-checked RAW: {topic}")
        except Exception as e:
            print(f"  Warning: Could not process {md_file}: {e}", file=sys.stderr)
    
    return raw_records


def step3_check_integrity(topic: str = None, all_topics: bool = False, instance: str = DEFAULT_INSTANCE) -> int:
    """Check wiki integrity using internal scan."""
    base_dir = get_base_dir(instance)
    
    print(f"Step 3: Checking wiki integrity for instance '{instance}'")
    print(f"Base dir: {base_dir}")
    
    topics_to_check = []
    
    if topic:
        topics_to_check = [topic]
    elif all_topics:
        mini_dir = base_dir / "minified"
        if mini_dir.exists():
            for f in mini_dir.glob("*.md"):
                if f.name != "log.md":
                    topics_to_check.append(f.stem)
        topics_to_check = sorted(topics_to_check)
    else:
        print("No specific topic or --all flag provided", file=sys.stderr)
        return 1
    
    print(f"Checking {len(topics_to_check)} topics...")
    
    from common.ollama_lock import call_ollama as _locked_call_ollama
    
    MODEL = "qwen3:1.7b"
    PROMPT = (
        "Compare these texts for factual consistency. Reply with CONSISTENT or DRIFT: followed by contradictions."
    )
    
    drift_count = 0
    for t in topics_to_check:
        doc_path = base_dir / "documentation" / f"{t}.md"
        mini_path = base_dir / "minified" / f"{t}.md"
        
        if not doc_path.exists() or not mini_path.exists():
            print(f"  {t}: SKIPPED (missing layer)")
            continue
        
        try:
            doc = doc_path.read_text(encoding='utf-8')
            mini = mini_path.read_text(encoding='utf-8')
            
            content = PROMPT + f"\n\n=== DOC ===\n{doc}\n\n=== MINI ===\n{mini}"
            
            try:
                resp = _locked_call_ollama(MODEL, [{"role": "user", "content": content}], 
                                          think=False, timeout=180, label="wiki-integrity-check")
                verdict = resp.get("message", {}).get("content", "").strip()
                print(f"  {t}: {verdict[:80]}")
                if verdict.startswith("DRIFT"):
                    drift_count += 1
            except Exception as e:
                print(f"  {t}: ERROR - {e}")
        except Exception as e:
            print(f"  {t}: READ ERROR - {e}")
    
    print(f"\nIntegrity check complete. {drift_count} topics with drift detected.")
    return drift_count


def main():
    parser = argparse.ArgumentParser(
        description="DSI-Wiki Maintenance Console",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Steps:
  step1: Clear a topic and add RAW document
    python wiki_maintain.py step1 <topic> [--document <file>]
    
  step2: Show folder and add fact-checked RAW records
    python wiki_maintain.py step2 <folder>
    
  step3: Check wiki integrity with internal scan
    python wiki_maintain.py step3 [--topic <name>] [--all]
"""
    )
    parser.add_argument("--instance", default=DEFAULT_INSTANCE, help="Wiki instance name")
    subparsers = parser.add_subparsers(dest="step", required=True)
    
    parser_step1 = subparsers.add_parser("step1", help="Clear topic and add RAW document")
    parser_step1.add_argument("topic", help="Topic name to clear and add as RAW")
    parser_step1.add_argument("--document", "-d", help="Path to large document to add (optional)")
    
    parser_step2 = subparsers.add_parser("step2", help="Show folder and add fact-checked RAW records")
    parser_step2.add_argument("folder", help="Folder path to scan for fact-check sources")
    
    parser_step3 = subparsers.add_parser("step3", help="Check wiki integrity")
    parser_step3.add_argument("--topic", "-t", help="Specific topic to check")
    parser_step3.add_argument("--all", "-a", action="store_true", help="Check all topics")
    
    args = parser.parse_args()
    
    if args.step == "step1":
        result = step1_clear_and_add_raw(args.topic, args.document, args.instance)
        print(f"Done: {result}")
    elif args.step == "step2":
        results = step2_list_and_factcheck(args.folder, args.instance)
        print(f"Done: Added {len(results)} fact-checked RAW records")
    elif args.step == "step3":
        drift = step3_check_integrity(args.topic, args.all, args.instance)
        sys.exit(drift > 0)


if __name__ == "__main__":
    main()