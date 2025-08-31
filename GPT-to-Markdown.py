#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Coding-Style:
# - Imports: json/sys/os -> Json/Sys/Os
# - Variablen: Mixed-Case mit Underscore, beginnen Uppercase
# - Listen-Variablen enden auf _List

import json as Json
import sys as Sys
import os as Os
import re as Re
from datetime import datetime as Datetime

# -----------------------------------------------------------------------------
# Utils
# -----------------------------------------------------------------------------

def Sanitize_Filename(Name):
	return Re.sub(r'[^a-zA-Z0-9._-]+', "_", Name)[:120] or "Chat.md"

def Next_Link(Ts):
	try:
		Dt = Datetime.fromtimestamp(Ts)
		Time_Str = Dt.strftime("%Y.%m.%d-%H:%M:%S")
		return f"[Bct-{Time_Str}](1000001.md)"
	except Exception:
		return f"[Bct-{Ts}](1000001.md)"

# -----------------------------------------------------------------------------
# Citations (Erkennung, Registry, Ersetzung)
# -----------------------------------------------------------------------------

def _extract_ids_from_marker_text(Text):
	# Extrahiert IDs aus Sequenzen \uE200 ... \uE201, trennt an \uE202
	# Erlaubt nur turn<Zahlen><Buchstaben><Zahlen> (z.B. turn0search4, turn1view0, turn0open3 ...)
	Id_List = []
	if not Text:
		return set()
	for Mo in Re.finditer(r'\uE200([\s\S]*?)\uE201', Text):
		Inner = Mo.group(1)
		for Tok in (Inner.split('\uE202') if Inner else []):
			Tok = (Tok or "").strip()
			if not Tok or Tok.lower() == "cite":
				continue
			if Re.match(r'^turn\d+[A-Za-z]+\d+$', Tok):
				Id_List.append(Tok)
	return set(Id_List)

def Canonicalize_Url(Url):
	try:
		from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
	except Exception:
		return Url
	if not Url:
		return Url
	P = urlparse(Url)
	Netloc = (P.netloc or "").lower()
	if Netloc.startswith("www."):
		Netloc = Netloc[4:]
	Path = P.path or ""
	if Path.endswith("/") and Path != "/":
		Path = Path[:-1]
	Skip_Set = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","utm_id","gclid","fbclid"}
	Query_List = [(k, v) for (k, v) in parse_qsl(P.query, keep_blank_values=True) if k not in Skip_Set]
	Query_List.sort()
	Query = urlencode(Query_List, doseq=True)
	return urlunparse((P.scheme, Netloc, Path, P.params, Query, P.fragment))

def Extract_Citations_From_Message(Msg):
	# Baut id->url Map, indem matched_text IDs mit nahen URLs gepaart werden.
	Cite_Map = {}

	def Pair_Ids_With_Urls(Id_List, Obj):
		Url_List = []

		# a) direktes 'url'
		if isinstance(Obj.get("url"), str) and Obj.get("url"):
			Url_List.append(Obj["url"])

		# b) 'safe_urls'
		Safe_List = Obj.get("safe_urls")
		if isinstance(Safe_List, list):
			for U in Safe_List:
				if isinstance(U, str) and U and U not in Url_List:
					Url_List.append(U)

		# c) 'items[*].url'
		Items_List = Obj.get("items")
		if isinstance(Items_List, list):
			for It in Items_List:
				if isinstance(It, dict) and isinstance(It.get("url"), str) and It["url"] and It["url"] not in Url_List:
					Url_List.append(It["url"])

		# d) 'fallback_items[*].url'
		Fb_List = Obj.get("fallback_items")
		if isinstance(Fb_List, list):
			for It in Fb_List:
				if isinstance(It, dict) and isinstance(It.get("url"), str) and It["url"] and It["url"] not in Url_List:
					Url_List.append(It["url"])

		# Zuweisung
		if Url_List:
			if len(Url_List) == len(Id_List):
				for Cid, U in zip(Id_List, Url_List):
					Cite_Map.setdefault(Cid, U)
			else:
				# Fallback: erste URL für alle IDs ohne Mapping
				for Cid in Id_List:
					if Cid not in Cite_Map:
						Cite_Map[Cid] = Url_List[0]

	def Walk(Obj):
		if isinstance(Obj, dict):
			Val_Id = Obj.get("id"); Val_Url = Obj.get("url")
			if isinstance(Val_Id, str) and isinstance(Val_Url, str) and Val_Id.strip():
				Cite_Map.setdefault(Val_Id.strip(), Val_Url.strip())

			Matched = Obj.get("matched_text")
			if isinstance(Matched, str) and ("\uE200" in Matched and "\uE201" in Matched):
				Ids = [i for i in _extract_ids_from_marker_text(Matched)]
				if Ids:
					Pair_Ids_With_Urls(Ids, Obj)

			for V in Obj.values():
				Walk(V)
		elif isinstance(Obj, list):
			for It in Obj:
				Walk(It)

	if isinstance(Msg, dict):
		Walk(Msg.get("metadata", {}))
		Walk(Msg)

	return Cite_Map

class CiteRegistry:
	def __init__(self):
		self.Id_To_Num_Dict = {}
		self.Id_To_Url_Dict = {}
		self.UrlKey_To_Num_Dict = {}
		self.Counter = 1

	def Register(self, Cite_Id, Url=""):
		Url = (Url or "").strip()
		Url_Key = Canonicalize_Url(Url) if Url else ""
		# Deduplizierung über kanonisierte URL
		if Url_Key and Url_Key in self.UrlKey_To_Num_Dict:
			N = self.UrlKey_To_Num_Dict[Url_Key]
			self.Id_To_Num_Dict.setdefault(Cite_Id, N)
			if Url and not self.Id_To_Url_Dict.get(Cite_Id):
				self.Id_To_Url_Dict[Cite_Id] = Url
			return N
		# Wiederverwendung bereits vergebener Nummer für die gleiche ID
		if Cite_Id in self.Id_To_Num_Dict:
			if Url and not self.Id_To_Url_Dict.get(Cite_Id):
				self.Id_To_Url_Dict[Cite_Id] = Url
			return self.Id_To_Num_Dict[Cite_Id]
		# Neue Nummer
		N = self.Counter
		self.Counter += 1
		self.Id_To_Num_Dict[Cite_Id] = N
		if Url_Key:
			self.UrlKey_To_Num_Dict[Url_Key] = N
			self.Id_To_Url_Dict[Cite_Id] = Url
		return N

	def Replace_Markers_With_S_Links(self, Text):
		# Ersetzt  Marker durch [Sx](#Sx); ignoriert Fremdtokens
		if not Text:
			return Text
		Allowed_Re = Re.compile(r'^turn\d+[A-Za-z]+\d+$')
		def Repl(Mo):
			Inner = Mo.group(1)
			Id_List = [I.strip() for I in (Inner.split('\uE202') if Inner else []) if I.strip()]
			Out_List = []
			Seen_Set = set()
			for Cid in Id_List:
				if Cid in Seen_Set:
					continue
				Seen_Set.add(Cid)
				if not Allowed_Re.match(Cid):
					continue
				N = self.Register(Cid, self.Id_To_Url_Dict.get(Cid, ""))
				Out_List.append(f"[\[S{N}\]](#S{N})")
			return " ".join(Out_List) if Out_List else ""
		Text = Re.sub(r'\uE200([\s\S]*?)\uE201', Repl, Text)
		Text = Re.sub(r'[\uE200\uE201\uE202]', '', Text)
		return Text

	def Extract_Domain(self, Url):
		from urllib.parse import urlparse
		# Parse Url
		Parsed = urlparse(Url)
		# Remove Port
		Netloc = Re.sub(r':\d+$', '', Parsed.netloc)
		# Capitalize Schema
		Schema = Parsed.scheme.capitalize()
		# Capitalize Parts of Netloc
		Parts = Netloc.split('.')
		Parts = [P[0].upper() + P[1:] if P else P for P in Parts]
		Netloc_Capitalized = '.'.join(Parts)
		# Build Result
		Domain = f"{Schema}://{Netloc_Capitalized}"
		return Domain

	def Sources_Section(self):
		# Eine Quelle (Sx) pro eindeutiger URL; listet ALLE zugehörigen IDs mit auf.
		if not self.Id_To_Num_Dict:
			return ""
		Out_List = ["## Sources <a id=\"100000\"/>", ""]

		# N -> Liste aller IDs
		Num_To_Ids_Dict = {}
		for Cid, N in self.Id_To_Num_Dict.items():
			Num_To_Ids_Dict.setdefault(N, []).append(Cid)

		for N in sorted(Num_To_Ids_Dict):
			Cid_List = sorted(Num_To_Ids_Dict[N])
			Cid_Primary = Cid_List[0]
			Url = ""
			for Cid in Cid_List:
				if Cid in self.Id_To_Url_Dict and self.Id_To_Url_Dict[Cid]:
					Url = self.Id_To_Url_Dict[Cid]
					break
			if Url:
				try:
					from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
					P = urlparse(Url)
					Q = dict(parse_qsl(P.query))
					Q["cite_id"] = Cid_Primary
					Url = urlunparse((P.scheme, P.netloc, P.path, P.params, urlencode(Q), P.fragment))
				except Exception:
					pass
				Domain_Name = self.Extract_Domain(Url)
				Out_List.append(f"- <a id=\"S{N}\"></a> [S{N}] [{Domain_Name}]({Url})")
				Out_List.append(f"  - Chat-GPT-Ids: {', '.join(Cid_List)}")
			else:
				Out_List.append(f"- <a id=\"S{N}\"></a> [S{N}] — ID: {Cid_Primary}  — ids: {', '.join(Cid_List)}")

		Out_List.append("")
		return "\n".join(Out_List)

def Build_Global_Citation_Map(Conv):
	# Sammelt id->url über alle Knoten der Konversation
	Mapping_Dict = Conv.get("mapping", {}) or {}
	Result_Dict = {}
	for Node in Mapping_Dict.values():
		Msg = (Node or {}).get("message") or {}
		Cm_Dict = Extract_Citations_From_Message(Msg)
		for K, V in Cm_Dict.items():
			if K not in Result_Dict:
				Result_Dict[K] = V
	return Result_Dict

# -----------------------------------------------------------------------------
# Dings Map
# -----------------------------------------------------------------------------

def Load_Dings_Map(Dings_Map_Path):
	if not Dings_Map_Path:
		return {}
	if not Os.path.isfile(Dings_Map_Path):
		raise SystemExit(f"Dings map file not found: {Dings_Map_Path}")
	with open(Dings_Map_Path, "r", encoding="utf-8") as F:
		Obj = Json.load(F)
	if not isinstance(Obj, dict):
		raise SystemExit("Dings map must be a JSON object with {Name:Number}")
	# Alles zu Strings
	return {K: str(V) for K, V in Obj.items() if isinstance(K, str)}

def Build_Dings_Regex_List(Dings_Map_Dict):
	Key_List = sorted(Dings_Map_Dict.keys(), key=len, reverse=True)
	Regex_List = []
	for Key in Key_List:
		Pat = Re.compile(rf'(?<!\w){Re.escape(Key)}(?!\w)', Re.UNICODE)
		Regex_List.append((Pat, Key, Dings_Map_Dict[Key]))
	return Regex_List

def Apply_Dings_Map(Text, Dings_Regex_List):
	if not Text or not Dings_Regex_List:
		return Text
	for Pat, Key, Num in Dings_Regex_List:
		Text = Pat.sub(f'[{Key}]({Num}.md)', Text)
	return Text

# -----------------------------------------------------------------------------
# Conversations & Nodes
# -----------------------------------------------------------------------------

def Load_Conversations(Json_Path):
	with open(Json_Path, "r", encoding="utf-8") as F:
		Data = Json.load(F)
	if isinstance(Data, dict) and "conversations" in Data:
		return Data["conversations"]
	if isinstance(Data, list):
		return Data
	raise ValueError("Unexpected JSON format: no 'conversations' key and not a list")

def List_Conversations(Json_Path):
	Conv_List = Load_Conversations(Json_Path)
	print("Available conversations:")
	for Conv in Conv_List:
		Cid = Conv.get("id")
		Title = Conv.get("title", "Untitled")
		Ts = Conv.get("update_time") or Conv.get("create_time")
		Ts_Str = (Datetime.fromtimestamp(Ts).isoformat(timespec="seconds") if isinstance(Ts, (int, float)) else "")
		if Ts_Str:
			print(f"- {Cid} : {Title}  ({Ts_Str})")
		else:
			print(f"- {Cid} : {Title}")

def Extract_Text_From_Node(Node):
	Msg = Node.get("message")
	if not Msg:
		return None, None, None, None, {}
	Author = (Msg.get("author", {}) or {}).get("role", "unknown")
	Role = str(Author).capitalize()
	Content = Msg.get("content", {}) or {}
	Part_List = Content.get("parts", []) or []
	Text_List = []
	for P in Part_List:
		if isinstance(P, str):
			Text_List.append(P)
		elif isinstance(P, dict) and isinstance(P.get("text"), str):
			Text_List.append(P["text"])
	Text = "\n\n".join(Text_List).strip()
	Ts = Msg.get("create_time") if isinstance(Msg.get("create_time"), (int, float)) else None
	Cite_Map = Extract_Citations_From_Message(Msg)
	return Role, Text, Ts, Node.get("id"), Cite_Map

def Conversation_Timestamp(Conv):
	T = Conv.get("update_time") or Conv.get("create_time")
	if T:
		return T
	Max_T = None
	for Node in (Conv.get("mapping", {}) or {}).values():
		_, _, Ts, _, _ = Extract_Text_From_Node(Node)
		if Ts is not None:
			Max_T = max(Max_T, Ts) if Max_T is not None else Ts
	return Max_T

def Sort_Nodes_By_Time(Node_List, Order="asc"):
	Packed_List = []
	for I, N in enumerate(Node_List):
		_, _, Ts, _, _ = Extract_Text_From_Node(N)
		Packed_List.append((1 if Ts is not None else 0, Ts or 0, I, N))
	if Order == "desc":
		Packed_List.sort(key=lambda T: (T[0], T[1], T[2]), reverse=True)
	else:
		Packed_List.sort(key=lambda T: (-T[0], T[1], T[2]))
	return [N for _, _, _, N in Packed_List]

def Build_Path_Nodes(Mapping_Dict, Current_Node_Id):
	if not Current_Node_Id or Current_Node_Id not in Mapping_Dict:
		return None
	Id_List_Rev = []
	Nid = Current_Node_Id
	Seen_Set = set()
	while Nid and Nid in Mapping_Dict and Nid not in Seen_Set:
		Seen_Set.add(Nid)
		Id_List_Rev.append(Nid)
		Nid = Mapping_Dict[Nid].get("parent")
	Id_List = list(reversed(Id_List_Rev))
	return [Mapping_Dict.get(Pid) for Pid in Id_List if isinstance(Mapping_Dict.get(Pid), dict)]

def Group_QA(Node_List):
	Pair_List = []
	Pending_Q = None
	for N in Node_List:
		Role, Text, Ts, _, Cite_Map = Extract_Text_From_Node(N)
		if not Text:
			continue
		if Role == "User":
			if Pending_Q is not None:
				Pair_List.append((Pending_Q, None))
			Pending_Q = (Role, Text, Ts, Cite_Map)
		elif Role == "Assistant":
			if Pending_Q is None:
				Pair_List.append((None, (Role, Text, Ts, Cite_Map)))
			else:
				Pair_List.append((Pending_Q, (Role, Text, Ts, Cite_Map)))
				Pending_Q = None
		else:
			# Sonstige Rollen als alleinstehende Einträge
			Pair_List.append(((Role, Text, Ts, Cite_Map), None))
	if Pending_Q is not None:
		Pair_List.append((Pending_Q, None))
	return Pair_List

# -----------------------------------------------------------------------------
# Export
# -----------------------------------------------------------------------------

def Export_One(Conv, Out_Path, Mode="time", Order="asc", Dings_Regex_List=None, Group_Mode="qa"):
	Title = "GPT-Chat-" + Conv.get("title", "Untitled") or "Untitled"
	Title = Title.replace(" ", "-")
	Ct = Conv.get("create_time")
	Ut = Conv.get("update_time")
	Mapping_Dict = Conv.get("mapping", {}) or {}

	# Node Auswahl
	Node_List = None
	if Mode == "path":
		Current_Node_Id = Conv.get("current_node")
		Node_List = Build_Path_Nodes(Mapping_Dict, Current_Node_Id) or None
	if Mode == "time" or Node_List is None:
		Node_List = list(Mapping_Dict.values())
		Node_List = Sort_Nodes_By_Time(Node_List, Order=Order)

	Line_List = [f"# {Title}", ""]
	Line_List.append("")
	Line_List.append("I am a Dings-GPT-Chat.")
	Line_List.append("")
	Line_List.append("## About <a id=\"0\"/>")
	Meta_List = []
	if Ct:
		Meta_List.append(f"Created: {Next_Link(Ct)}")
	if Ut:
		Meta_List.append(f"Updated: {Next_Link(Ut)}")
	if Meta_List:
		Line_List += [f"_{'  •  '.join(Meta_List)}_", ""]

	# Zitat-Registry vorbefüllen (damit URLs bekannt sind)
	Cite_Reg = CiteRegistry()
	for _Cid, _Url in Build_Global_Citation_Map(Conv).items():
		Cite_Reg.Register(_Cid, _Url)

	# Inhalt schreiben
	if Group_Mode == "qa":
		Pair_List = Group_QA(Node_List)
		for I, (Q, A) in enumerate(Pair_List, start=1):
			Line_List.append(f"## QA-{I:04d} <a id=\"{I}\"/>")
			Line_List.append("")
			Line_List.append('<div style="border:1px solid #e5e7eb; padding:1em; border-radius:8px;">')

			if Q is not None:
				_, Q_Text, Q_Ts, Q_Cites = Q
				for Cid, Url in (Q_Cites or {}).items():
					Cite_Reg.Register(Cid, Url)
				Q_Text = Cite_Reg.Replace_Markers_With_S_Links(Q_Text)
				if Dings_Regex_List:
					Q_Text = Apply_Dings_Map(Q_Text, Dings_Regex_List)
				Line_List.append('<div style="background-color:#ffffff; padding:0.6em; border-radius:6px;">')
				if Q_Ts:
					Line_List.append(f"<div>{Next_Link(Q_Ts)}</div>")
				Line_List.append("")
				Line_List.append(Q_Text)
				Line_List.append("</div>")
				Line_List.append("")

			if A is not None:
				_, A_Text, A_Ts, A_Cites = A
				for Cid, Url in (A_Cites or {}).items():
					Cite_Reg.Register(Cid, Url)
				A_Text = Cite_Reg.Replace_Markers_With_S_Links(A_Text)
				if Dings_Regex_List:
					A_Text = Apply_Dings_Map(A_Text, Dings_Regex_List)
				Line_List.append('<div style="background-color:#f3f4f6; padding:0.6em; border-radius:6px; margin-top:0.6em;">')
				if A_Ts:
					Line_List.append(f"<div>{Next_Link(A_Ts)}</div>")
				Line_List.append("")
				Line_List.append(A_Text)
				Line_List.append("</div>")
				Line_List.append("")

			Line_List.append("</div>")
			Line_List.append("")
			Line_List.append("---")
			Line_List.append("---")
			Line_List.append("")
	else:
		# Ungruppiert (falls gewünscht)
		for Node in Node_List:
			Role, Text, Ts, _, Cite_Map = Extract_Text_From_Node(Node)
			if not Text:
				continue
			for Cid, Url in (Cite_Map or {}).items():
				Cite_Reg.Register(Cid, Url)
			Text = Cite_Reg.Replace_Markers_With_S_Links(Text)
			if Dings_Regex_List:
				Text = Apply_Dings_Map(Text, Dings_Regex_List)
			Line_List.append(f"### {Role}")
			if Ts:
				Line_List.append(Next_Link(Ts))
			Line_List.append("")
			Line_List.append(Text)
			Line_List.append("")
			Line_List.append("---")
			Line_List.append("---")
			Line_List.append("")

	# Markdown zusammenbauen
	Md = "\n".join(Line_List).strip() + "\n"
	# Sicherheitsnetz: Zitatmarker, die evtl. aus Metadaten noch drin sind, ersetzen
	Md = Cite_Reg.Replace_Markers_With_S_Links(Md)
	# Sources anfügen
	Src_Sect = Cite_Reg.Sources_Section()
	if Src_Sect:
		Md = Md + "\n" + Src_Sect + "\n"

	if not Out_Path:
		Out_Path = Sanitize_Filename(f"{Title}.md")
	with open(Out_Path, "w", encoding="utf-8") as F:
		F.write(Md)
	print(f"Wrote: {Out_Path}")

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def Print_Usage():
	print("Usage:")
	print("  GPT-to-Markdown.py <conversations.json> [--list]")
	print("  GPT-to-Markdown.py <conversations.json> --id <conversation_id> [out.md]")
	print("    [--mode path|time] [--order asc|desc] [--dings-map FILE] [--group qa|none]")

def Parse_Arg_Value(Arg_List, Flag, Allowed=None, Default=None):
	if Flag in Arg_List:
		I = Arg_List.index(Flag)
		if I + 1 < len(Arg_List):
			Val = Arg_List[I + 1]
			if (Allowed is None) or (Val in Allowed):
				return Val
	return Default

def Strip_Flag_With_Value(Arg_List, Flag):
	if Flag in Arg_List:
		I = Arg_List.index(Flag)
		if I + 1 < len(Arg_List):
			Arg_List = Arg_List[:I] + Arg_List[I+2:]
		else:
			Arg_List = Arg_List[:I] + Arg_List[I+1:]
	return Arg_List

def Main():
	if len(Sys.argv) < 2:
		Print_Usage()
		Sys.exit(1)

	Json_Path = Sys.argv[1]
	if not Os.path.isfile(Json_Path):
		print(f"File not found: {Json_Path}")
		Sys.exit(1)

	# Neuer Modus: nur alle Konversationen auflisten
	if "--list" in Sys.argv[2:]:
		List_Conversations(Json_Path)
		Sys.exit(0)

	Conv_List = Load_Conversations(Json_Path)

	Arg_List = Sys.argv[2:]
	Mode = Parse_Arg_Value(Arg_List, "--mode", Allowed=("path","time"), Default="time")
	Order = Parse_Arg_Value(Arg_List, "--order", Allowed=("asc","desc"), Default="asc")
	Dings_Map_Path = Parse_Arg_Value(Arg_List, "--dings-map")
	Group_Mode = Parse_Arg_Value(Arg_List, "--group", Allowed=("qa","none"), Default="qa")

	# Flags aus Arg_List entfernen
	Arg_List = Strip_Flag_With_Value(Arg_List, "--mode")
	Arg_List = Strip_Flag_With_Value(Arg_List, "--order")
	if Dings_Map_Path:
		Arg_List = Strip_Flag_With_Value(Arg_List, "--dings-map")
	Arg_List = Strip_Flag_With_Value(Arg_List, "--group")

	# Out_Path ermitteln
	Out_Path = ""
	if len(Arg_List) >= 3 and not Arg_List[-2].startswith("--"):
		Out_Path = Arg_List[-1]

	# Auswahl per --id
	if Arg_List and Arg_List[0] == "--id" and len(Arg_List) >= 2:
		Target_Id = Arg_List[1]
		Conv = None
		for C in Conv_List:
			if str(C.get("id")) == Target_Id:
				Conv = C
				break
		if not Conv:
			print(f"Conversation not found for id: {Target_Id}")
			Sys.exit(1)

		# Dings Map laden
		Dings_Regex_List = Build_Dings_Regex_List(Load_Dings_Map(Dings_Map_Path)) if Dings_Map_Path else None

		Export_One(Conv, Out_Path, Mode=Mode, Order=Order, Dings_Regex_List=Dings_Regex_List, Group_Mode=Group_Mode)
	else:
		Print_Usage()
		Sys.exit(1)

if __name__ == "__main__":
	Main()

