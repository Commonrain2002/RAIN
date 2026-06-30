using System.Text.Json.Serialization;

namespace ProofAgent.Coq;

/// <summary>JSON envelope for parse-script stdout; see <c>Docs/parse_sentence_contract.md</c>.</summary>
public class CoqParseSentenceScriptJsonEnvelope
{
    [JsonPropertyName("sentences")]
    public List<CoqSentence>? Sentences { get; init; }
}
