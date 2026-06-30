(**************************************************************************)
(* Split a .v file into Rocq parser sentences (same pipeline as VsRocq IDE). *)
(**************************************************************************)
open Base
open Dm
open Vernacexpr
open Synterp

type vernac_sentence_info = { vernac_type: string; name: string }

let id_to_string = Names.Id.to_string

let name_of_lname = function
  | Names.Anonymous -> ""
  | Names.Name n -> id_to_string n

let first_of_list = function
  | [] -> ""
  | n :: _ -> n

let name_of_inductive_exprs (l : (inductive_expr * notation_declaration list) list) =
  match l with
  | [] -> ""
  | (((_, ({ CAst.v = id }, _)), _, _, _), _) :: _ -> id_to_string id

[%%if rocq = "8.18" || rocq = "8.19" || rocq = "8.20"]
let name_of_fixpoints_expr (l : fixpoint_expr list) =
  match l with
  | [] -> ""
  | { fname = { CAst.v = id } } :: _ -> id_to_string id

let name_of_cofixpoints_expr (l : cofixpoint_expr list) =
  match l with
  | [] -> ""
  | { fname = { CAst.v = id } } :: _ -> id_to_string id
[%%else]
let name_of_recursive_exprs (l : recursive_expr_gen list) =
  match l with
  | [] -> ""
  | { fname = { CAst.v = id } } :: _ -> id_to_string id

let name_of_fixpoints_expr ((_, exprs) : fixpoints_expr) =
  name_of_recursive_exprs exprs

let name_of_cofixpoints_expr (exprs : cofixpoints_expr) =
  name_of_recursive_exprs exprs
[%%endif]

let vernac_info_of_synterp (e : synterp_entry) : vernac_sentence_info =
  match e with
  | EVernacRequire (_, _, _, imports) ->
      let name =
        List.map imports ~f:(fun (q, _) -> Libnames.string_of_qualid q) |> first_of_list
      in
      { vernac_type = "require"; name }
  | EVernacImport _ -> { vernac_type = "import"; name = "" }
  | EVernacBeginSection { CAst.v = id } ->
      { vernac_type = "section"; name = id_to_string id }
  | EVernacEndSegment { CAst.v = id } ->
      { vernac_type = "section"; name = id_to_string id }
  | EVernacNotation _ -> { vernac_type = "notation"; name = "" }
  | EVernacSetOption _ -> { vernac_type = "option"; name = "" }
  | EVernacLoad _ -> { vernac_type = "load"; name = "" }
  | EVernacExtend _ -> { vernac_type = "plugin"; name = "" }
  | EVernacDeclareModule (_, { CAst.v = id }, _, _)
  | EVernacDefineModule (_, { CAst.v = id }, _, _, _, _)
  | EVernacDeclareModuleType ({ CAst.v = id }, _, _, _, _) ->
      { vernac_type = "module"; name = id_to_string id }
  | EVernacInclude _ -> { vernac_type = "include"; name = "" }
  | EVernacNoop -> { vernac_type = "noop"; name = "" }

let vernac_info_of_pure (pure : synpure_vernac_expr) : vernac_sentence_info =
  match pure with
  | VernacDefinition (_, ({ CAst.v = name }, _), DefineBody _) ->
      { vernac_type = "definition"; name = name_of_lname name }
  | VernacDefinition (_, ({ CAst.v = name }, _), ProveBody _) ->
      { vernac_type = "theorem"; name = name_of_lname name }
  | VernacStartTheoremProof (_, proofs) ->
      let name =
        List.map proofs ~f:(fun (({ CAst.v = id }, _), _) -> id_to_string id) |> first_of_list
      in
      { vernac_type = "theorem"; name }
  | VernacInductive (_, exprs) ->
      { vernac_type = "inductive"; name = name_of_inductive_exprs exprs }
  | VernacFixpoint (_, exprs) ->
      { vernac_type = "fixpoint"; name = name_of_fixpoints_expr exprs }
  | VernacCoFixpoint (_, exprs) ->
      { vernac_type = "cofixpoint"; name = name_of_cofixpoints_expr exprs }
  | VernacAssumption (_, _, groups) ->
      let name =
        List.concat_map groups ~f:(fun (_, (decls, _)) ->
            List.map decls ~f:(fun ({ CAst.v = id }, _) -> id_to_string id))
        |> first_of_list
      in
      { vernac_type = "assumption"; name }
  | VernacPrimitive (({ CAst.v = id }, _), _, _) ->
      { vernac_type = "primitive"; name = id_to_string id }
  | _ -> { vernac_type = "other"; name = "" }

let vernac_info_of_ast (ast : vernac_control_entry) : vernac_sentence_info =
  match ast.v.expr with
  | VernacSynterp e -> vernac_info_of_synterp e
  | VernacSynPure pure -> vernac_info_of_pure pure

let name_from_classification (c : Vernacextend.vernac_classification) =
  match c with
  | Vernacextend.VtStartProof (_, ids) | VtSideff (ids, _) -> (
      match ids with
      | [] -> ""
      | id :: _ -> Names.Id.to_string id)
  | _ -> ""

let enrich_info_from_classification info classification =
  match (info.vernac_type, classification) with
  | "other", Vernacextend.VtStartProof _ -> { info with vernac_type = "theorem" }
  | _ -> info

let vernac_info_of_sentence (s : Document.sentence) : vernac_sentence_info * string list =
  match s.Document.ast with
  | Error _ -> ({ vernac_type = "parse_error"; name = "" }, [])
  | Parsed { ast; classification; tokens } ->
      let info =
        enrich_info_from_classification (vernac_info_of_ast ast) classification
      in
      let name =
        if String.is_empty info.name then name_from_classification classification else info.name
      in
      let info = { info with name } in
      let lex_tokens =
        List.filter_map tokens ~f:(fun tok ->
            let s = Tok.extract_string false tok in
            if String.is_empty s then None else Some s)
      in
      (info, lex_tokens)

(** Same discovery order as [vsrocqtop/args.ml]: [_RocqProject] then [_CoqProject],
    rooted at the [.v] file's directory (not necessarily cwd). *)
let coqtop_cli_args_from_project_search_dir dir =
  let find pf =
    CoqProject_file.find_project_file ~from:dir ~projfile_name:pf
  in
  let project_file =
    match find "_RocqProject" with Some _ as x -> x | None -> find "_CoqProject"
  in
  match project_file with
  | None -> []
  | Some f ->
      let project = CoqProject_file.read_project_file ~warning_fn:(fun _ -> ()) f in
      CoqProject_file.coqtop_args_from_project project

[%%if rocq = "8.18" || rocq = "8.19" || rocq = "8.20"]
let init_coq_and_injections ~project_search_dir =
  Coqinit.init_ocaml ();
  let usage =
    Boot.Usage.{ executable_name = "vsrocq_split_sentences"; extra_args = ""; extra_options = "" }
  in
  let cmdline_args = coqtop_cli_args_from_project_search_dir project_search_dir in
  let opts, _ = Coqargs.parse_args ~usage ~init:Coqargs.default cmdline_args in
  Coqinit.init_runtime opts
[%%else]
let init_coq_and_injections ~project_search_dir =
  Coqinit.init_ocaml ();
  let usage =
    Boot.Usage.{ executable_name = "vsrocq_split_sentences"; extra_args = ""; extra_options = "" }
  in
  let cmdline_args = coqtop_cli_args_from_project_search_dir project_search_dir in
  let opts, _ = Coqargs.parse_args ~init:Coqargs.default cmdline_args in
  Coqinit.init_runtime ~usage opts;
  Coqinit.init_document opts;
  Coqargs.injection_commands opts
[%%endif]

let rec drive_parse max_steps (events : Document.event Sel.Todo.t) st =
  if max_steps <= 0 then
    failwith
      "vsrocq_split_sentences: exceeded step limit while parsing (file too large or \
       upstream bug)"
  else if Sel.Todo.is_empty events then failwith "vsrocq_split_sentences: empty event queue"
  else
    let ready, remaining = Sel.pop_timeout ~stop_after_being_idle_for:0.1 events in
    match ready with
    | None -> failwith "vsrocq_split_sentences: no ready parse event"
    | Some ev -> (
        match Document.handle_event st ev with
        | st, new_events, None ->
            let todo = Sel.Todo.add remaining new_events in
            drive_parse (max_steps - 1) todo st
        | _, new_events, Some update ->
            if not (Sel.Todo.is_empty (Sel.Todo.add remaining new_events)) then
              failwith "vsrocq_split_sentences: unexpected trailing events after parse end";
            update)

let shorten_coq_message s =
  match String.substr_index s ~pattern:"\nRaised at" with
  | None -> s
  | Some i -> String.sub s ~pos:0 ~len:i

let json_escape s =
  let b = Buffer.create (String.length s + 8) in
  String.iter s ~f:(fun c ->
      match c with
      | '"' -> Buffer.add_string b "\\\""
      | '\\' -> Buffer.add_string b "\\\\"
      | '\b' -> Buffer.add_string b "\\b"
      | '\n' -> Buffer.add_string b "\\n"
      | '\r' -> Buffer.add_string b "\\r"
      | '\t' -> Buffer.add_string b "\\t"
      | c ->
          let code = Char.to_int c in
          if code < 0x20 then Stdlib.Printf.bprintf b "\\u%04x" code else Buffer.add_char b c);
  Buffer.contents b

let json_string_list items =
  "[" ^ String.concat ~sep:", " (List.map items ~f:(fun s -> "\"" ^ json_escape s ^ "\"")) ^ "]"

(** [Vernacextend.vernac_classification] rendered for JSON ([ParseError] if the sentence did not parse). *)
let string_of_vernac_keep_as : Vernacextend.vernac_keep_as -> string = function
  | VtKeepAxiom -> "VtKeepAxiom"
  | VtKeepDefined -> "VtKeepDefined"
  | VtKeepOpaque -> "VtKeepOpaque"

let string_of_vernac_qed_type : Vernacextend.vernac_qed_type -> string = function
  | VtDrop -> "VtDrop"
  | VtKeep k -> Stdlib.Printf.sprintf "VtKeep(%s)" (string_of_vernac_keep_as k)

let string_of_vernac_when : Vernacextend.vernac_when -> string = function
  | VtNow -> "VtNow"
  | VtLater -> "VtLater"

let string_of_vernac_classification (c : Vernacextend.vernac_classification) =
  match c with
  | VtStartProof (opaque, ids) ->
      let op =
        match opaque with
        | GuaranteesOpacity -> "GuaranteesOpacity"
        | Doesn'tGuaranteeOpacity -> "Doesn'tGuaranteeOpacity"
      in
      let names = List.map ids ~f:Names.Id.to_string |> String.concat ~sep:"," in
      Stdlib.Printf.sprintf "VtStartProof(%s,[%s])" op names
  | VtSideff (ids, w) ->
      let names = List.map ids ~f:Names.Id.to_string |> String.concat ~sep:"," in
      Stdlib.Printf.sprintf "VtSideff([%s],%s)" names (string_of_vernac_when w)
  | VtQed q -> Stdlib.Printf.sprintf "VtQed(%s)" (string_of_vernac_qed_type q)
  | VtProofStep { proof_block_detection } -> (
      match proof_block_detection with
      | None -> "VtProofStep"
      | Some name -> Stdlib.Printf.sprintf "VtProofStep(%s)" name)
  | VtQuery -> "VtQuery"
  | VtProofMode pm ->
      Stdlib.Printf.sprintf "VtProofMode(%s)" (Pvernac.proof_mode_to_string pm)
  | VtMeta -> "VtMeta"

let classification_of_sentence (s : Document.sentence) =
  match s.Document.ast with
  | Error _ -> "ParseError"
  | Parsed { classification; _ } -> string_of_vernac_classification classification

let print_json ~path ~doc =
  let raw = Document.raw_document doc in
  let sentences = Document.sentences_sorted_by_loc doc in
  let errors = Document.parse_errors doc in
  Stdlib.Printf.printf
    "{\n  \"file\": \"%s\",\n\
  \  \"position_indexing\": {\"line\": \"1-based\", \"column\": \"0-based\"},\n\
  \  \"sentences\": [\n" (json_escape path);
  let first = ref true in
  List.iteri sentences ~f:(fun i s ->
      let sep = if !first then (first := false; "") else ",\n" in
      let text = RawDocument.string_in_range raw s.Document.start s.Document.stop in
      let p0 = RawDocument.position_of_loc raw s.Document.start in
      let p1 = RawDocument.position_of_loc raw s.Document.stop in
      let cls = classification_of_sentence s in
      let info, lex_tokens = vernac_info_of_sentence s in
      Stdlib.Printf.printf
        "%s    {\"index\": %d, \"byte_start\": %d, \"byte_end\": %d, \"start_line\": %d, \
         \"start_column\": %d, \"end_line\": %d, \"end_column\": %d, \"classification\": \"%s\", \
         \"vernac_type\": \"%s\", \"name\": \"%s\", \"tokens\": %s, \"text\": \"%s\"}"
        sep i s.Document.start s.Document.stop
        (p0.Lsp.Types.Position.line + 1) p0.Lsp.Types.Position.character
        (p1.Lsp.Types.Position.line + 1) p1.Lsp.Types.Position.character (json_escape cls)
        (json_escape info.vernac_type) (json_escape info.name) (json_string_list lex_tokens)
        (json_escape text));
  Stdlib.Printf.printf "\n  ],\n  \"parse_errors\": [\n";
  let first_err = ref true in
  List.iter errors ~f:(fun e ->
      let sep = if !first_err then (first_err := false; "") else ",\n" in
      let q0 = RawDocument.position_of_loc raw e.start in
      let q1 = RawDocument.position_of_loc raw e.stop in
      let message = shorten_coq_message (Pp.string_of_ppcmds (snd e.msg)) in
      Stdlib.Printf.printf
        "%s    {\"byte_start\": %d, \"byte_end\": %d, \"start_line\": %d, \"start_column\": %d, \
         \"end_line\": %d, \"end_column\": %d, \"text\": \"%s\", \"message\": \"%s\"}"
        sep e.start e.stop
        (q0.Lsp.Types.Position.line + 1) q0.Lsp.Types.Position.character
        (q1.Lsp.Types.Position.line + 1) q1.Lsp.Types.Position.character (json_escape e.str)
        (json_escape message));
  Stdlib.Printf.printf "\n  ]\n}\n%!"

let abs_path p =
  if Stdlib.Filename.is_relative p then
    Stdlib.Filename.concat (Stdlib.Sys.getcwd ()) p
  else p

let () =
  if Array.length Stdlib.Sys.argv <> 2 then (
    Stdlib.Printf.eprintf "Usage: %s <file.v>\n" Stdlib.Sys.argv.(0);
    Stdlib.exit 2);
  let path = abs_path Stdlib.Sys.argv.(1) in
  let project_search_dir = Stdlib.Filename.dirname path in
  let injections = init_coq_and_injections ~project_search_dir in
  let init_state = Vernacstate.freeze_full_state () in
  let text =
    try Stdlib.In_channel.with_open_bin path Stdlib.In_channel.input_all
    with Sys_error m ->
      Stdlib.Printf.eprintf "vsrocq_split_sentences: %s\n" m;
      Stdlib.exit 1
  in
  let uri = Lsp.Types.DocumentUri.of_path path in
  let st, _init_ev = DocumentManager.init init_state ~opts:injections uri ~text in
  let doc0 = DocumentManager.Internal.document st in
  let doc1, evs = Document.validate_document doc0 in
  let todo = Sel.Todo.(add empty evs) in
  let max_steps = 100_000 + (String.length text / 2) in
  let update = drive_parse max_steps todo doc1 in
  let st = DocumentManager.Internal.validate_document st update in
  let doc = DocumentManager.Internal.document st in
  print_json ~path ~doc
