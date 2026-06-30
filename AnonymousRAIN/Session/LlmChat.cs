using ProofAgent.Llm;

namespace ProofAgent.Session;

public class LlmChat
{
    #region Fields

    private readonly string _LastAssistantText;

    private readonly LlmUsage _TotalUsage;

    private readonly bool _ExceededMaxToolRounds;

    #endregion Fields

    #region Properties

    public string LastAssistantText => _LastAssistantText;

    /// <summary>Sum of usage over all HTTP completions in this <see cref="ILlmSession.ChatAsync"/> call.</summary>
    public LlmUsage TotalUsage => _TotalUsage;

    public bool ExceededMaxToolRounds => _ExceededMaxToolRounds;

    #endregion Properties

    public LlmChat(string lastAssistantText = "", LlmUsage totalUsage = default, bool exceededMaxToolRounds = false)
    {
        _LastAssistantText = lastAssistantText;
        _TotalUsage = totalUsage;
        _ExceededMaxToolRounds = exceededMaxToolRounds;
    }
}
