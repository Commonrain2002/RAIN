using System.Text.Json.Serialization;

namespace ProofAgent.Cli;

public class ProofAgentRunConfigDocument
{
    [JsonPropertyName("projectRoot")]
    public string? ProjectRoot { get; set; }

    [JsonPropertyName("targetCoqFile")]
    public string? TargetCoqFile { get; set; }

    [JsonPropertyName("userMessage")]
    public string? UserMessage { get; set; }

    [JsonPropertyName("checkCommand")]
    public string? CheckCommand { get; set; }

    [JsonPropertyName("parseSentenceScript")]
    public string? ParseSentenceScript { get; set; }

    [JsonPropertyName("checkTimeoutSeconds")]
    public int? CheckTimeoutSeconds { get; set; }

    [JsonPropertyName("searchHitContextLines")]
    public int? SearchHitContextLines { get; set; }

    [JsonPropertyName("extraErrorCount")]
    public int? ExtraErrorCount { get; set; }

    [JsonPropertyName("baseUrl")]
    public string? BaseUrl { get; set; }

    [JsonPropertyName("model")]
    public string? Model { get; set; }

    [JsonPropertyName("reasoningEffort")]
    public string? ReasoningEffort { get; set; }

    [JsonPropertyName("thinking")]
    public string? Thinking { get; set; }

    [JsonPropertyName("llmHttpTimeoutSeconds")]
    public int? LlmHttpTimeoutSeconds { get; set; }

    [JsonPropertyName("extraReadableRootPaths")]
    public List<string>? ExtraReadableRootPaths { get; set; }
}
