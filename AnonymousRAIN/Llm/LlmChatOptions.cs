namespace ProofAgent.Llm;

public class LlmChatOptions
{
    #region Fields

    private readonly bool _EnableReasoning;

    private readonly string _ReasoningEffort;

    private readonly string _ReasoningSummary;

    #endregion Fields

    #region Properties

    public bool EnableReasoning => _EnableReasoning;

    public string ReasoningEffort => _ReasoningEffort;

    /// <summary>OpenAI Responses-style <c>reasoning.summary</c> (e.g. <c>auto</c>); empty when summaries are not requested.</summary>
    public string ReasoningSummary => _ReasoningSummary;

    #endregion Properties

    public LlmChatOptions(bool enableReasoning, string reasoningEffort, string reasoningSummary = "auto")
    {
        if (string.IsNullOrWhiteSpace(reasoningEffort))
        {
            throw new ArgumentException("reasoningEffort must not be empty.", nameof(reasoningEffort));
        }

        _EnableReasoning = enableReasoning;
        _ReasoningEffort = reasoningEffort.Trim();
        if (!enableReasoning)
        {
            _ReasoningSummary = "";
            return;
        }

        var trimmedSummary = (reasoningSummary ?? "").Trim();
        _ReasoningSummary = trimmedSummary.Length == 0 ? "auto" : trimmedSummary;
    }
}
