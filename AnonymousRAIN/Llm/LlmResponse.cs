namespace ProofAgent.Llm;

public class LlmResponse
{
    #region Fields

    private readonly string _Text;

    private readonly IReadOnlyList<ToolCall> _ToolCalls;

    private readonly string? _ReasoningText;

    private readonly string? _ReasoningSummaryText;

    private readonly LlmUsage _Usage;

    #endregion Fields

    #region Properties

    public string Text => _Text;

    public IReadOnlyList<ToolCall> ToolCalls => _ToolCalls;

    public string? ReasoningText => _ReasoningText;

    /// <summary>Human-readable reasoning summary when the API returns one (OpenAI <c>reasoning.summary</c>).</summary>
    public string? ReasoningSummaryText => _ReasoningSummaryText;

    public LlmUsage Usage => _Usage;

    #endregion Properties

    public LlmResponse(
        string text,
        IReadOnlyList<ToolCall> toolCalls,
        string? reasoningText = null,
        LlmUsage usage = default,
        string? reasoningSummaryText = null)
    {
        _Text = text;
        _ToolCalls = toolCalls;
        _ReasoningText = reasoningText;
        _ReasoningSummaryText = reasoningSummaryText;
        _Usage = usage;
    }
}
