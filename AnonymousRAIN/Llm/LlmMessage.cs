namespace ProofAgent.Llm;

public class LlmMessage
{
    #region Fields

    private readonly LlmParticipantRole _Role;

    private readonly string _Content;

    private readonly IReadOnlyList<ToolCall> _AssistantToolCalls;

    private readonly string _ToolCallID;

    private readonly string _AssistantReasoningContent;

    #endregion Fields

    #region Properties

    public LlmParticipantRole Role => _Role;

    public string Content => _Content;

    public IReadOnlyList<ToolCall> AssistantToolCalls => _AssistantToolCalls;

    public string ToolCallID => _ToolCallID;

    /// <summary>In thinking mode, prior assistant <c>reasoning_content</c>; must be echoed when resubmitting after tool calls (sibling of <see cref="Content"/>).</summary>
    public string AssistantReasoningContent => _AssistantReasoningContent;

    #endregion Properties

    public static LlmMessage CreateSystem(string content)
    {
        return new LlmMessage(LlmParticipantRole.System, content, Array.Empty<ToolCall>(), "", "");
    }

    public static LlmMessage CreateUser(string content)
    {
        return new LlmMessage(LlmParticipantRole.User, content, Array.Empty<ToolCall>(), "", "");
    }

    public static LlmMessage CreateAssistant(
        string content,
        IReadOnlyList<ToolCall> toolCalls,
        string assistantReasoningContent = "")
    {
        return new LlmMessage(
            LlmParticipantRole.Assistant,
            content,
            toolCalls ?? Array.Empty<ToolCall>(),
            "",
            assistantReasoningContent);
    }

    public static LlmMessage CreateTool(string toolCallID, string content)
    {
        return new LlmMessage(LlmParticipantRole.Tool, content, Array.Empty<ToolCall>(), toolCallID, "");
    }

    private LlmMessage(
        LlmParticipantRole role,
        string content,
        IReadOnlyList<ToolCall> assistantToolCalls,
        string toolCallID,
        string assistantReasoningContent)
    {
        _Role = role;
        _Content = content;
        _AssistantToolCalls = assistantToolCalls;
        _ToolCallID = toolCallID;
        _AssistantReasoningContent =
            role == LlmParticipantRole.Assistant ? assistantReasoningContent : "";
    }
}
