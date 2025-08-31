CHAT_ID = 68b18159-75f8-8322-9032-8a646dc16375
MARKDOWN_FILE = /Users/michaelholzheu/All-Dings/111/.Dings/Repositories/0/308000011.md

$(MARKDOWN_FILE): GPT-to-Markdown.py conversations.json
	./GPT-to-Markdown.py conversations.json --id $(CHAT_ID) $(MARKDOWN_FILE) --mode path --dings-map All-Dings.dings-map
	cp 68b18159-75f8-8322-9032-8a646dc16375.md /Users/michaelholzheu/All-Dings/111/.Dings/Repositories/0/308000011.md

list:
	./GPT-to-Markdown.py conversations.json --list

pretty: conversations-pretty.json

conversations-pretty.json: conversations.json
	 python3 -m json.tool conversations.json > conversations-pretty.json

.PHONY: list pretty
