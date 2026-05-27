# Idea Basket — {{NAME}}

Ideas the autoresearch loop can draw on. Optional: if this file is absent, the loop
uses its own ideas. This file is **git-untracked** so it survives the loop's resets.

Line format (one idea per line, managed by basket.py — don't hand-edit the fields):
  - [ ] <one-line idea> — status: pending — source: <user | paper:"title" link | doc:file | web link | agent>

Status lifecycle:  pending -> doing -> selected (kept)  |  discarded (reverted).
Checkbox mirrors status:  [ ] pending · [~] doing · [x] selected · [-] discarded.
Drop reference documents (pdf/txt/html/md) into ./idea_basket/ — they are studied
and only ideas that align with the spec's goal are added.

## Ideas
