# Preset: talking head / interview / tutorial / podcast video

Use when people speak to camera or to each other and the words carry the story.

## Before planning
Run `FC transcribe "<WORK>"` (local faster-whisper, free). Plan from `transcript.md`, not from the pictures.
Use the contact sheets only to check framing, eyes closed, people walking in, etc.

## Rules
- Keep whole sentences. Cut in pauses of 0.4 s or more; 0.15-0.4 s only after checking a strip; never inside a word.
- Pad cuts with about 50 ms before the first word and 80 ms after the last word.
- Remove false starts, repeated takes (keep the last clean one), long "um/uh" pauses, off-topic chatter.
- Keep laughs and natural reactions - they make the cut feel human.
- When two speakers trade lines, leave 0.4-0.6 s of air at the hand-off.
- Several takes of the same line: choose the clearest delivery with the best framing.
- Jump cuts inside one continuous shot are normal for this style; warn only if the user asked for seamless cuts.

## Sound
Always keep the original sound. Never mute a speaking segment.

## Default length
Whatever the content needs; for social clips 30-90 s built from the strongest self-contained idea.
