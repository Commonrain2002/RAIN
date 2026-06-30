using System.Text.Json.Serialization;

namespace ProofAgent.Coq;

public class CoqSentence
{
    [JsonPropertyName("index")]
    public int Index { get; init; }

    [JsonPropertyName("start_line")]
    public int StartLineOneBased { get; init; }

    [JsonPropertyName("start_column")]
    public int StartColumnZeroBased { get; init; }

    [JsonPropertyName("end_line")]
    public int EndLineOneBased { get; init; }

    [JsonPropertyName("end_column")]
    public int EndColumnZeroBased { get; init; }

    [JsonPropertyName("text")]
    public string Text { get; init; } = "";

    /// <summary>
    /// Parsed from splitter <c>vernac_type</c>; see <c>Docs/parse_sentence_contract.md</c>.
    /// </summary>
    [JsonPropertyName("vernac_type")]
    [JsonConverter(typeof(CoqSentenceVernacTypeJsonConverter))]
    public CoqSentenceVernacType VernacType { get; init; }

    [JsonPropertyName("name")]
    public string Name { get; init; } = "";

    [JsonPropertyName("tokens")]
    public List<string> Tokens { get; init; } = new();

    /// <summary>
    /// Parsed from CoqStoq classification string; see <c>Docs/parse_sentence_contract.md</c>.
    /// </summary>
    [JsonPropertyName("classification")]
    [JsonConverter(typeof(CoqSentenceClassificationJsonConverter))]
    public CoqSentenceClassification Classification { get; init; }
}
