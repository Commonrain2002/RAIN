using ProofAgent.Coq;
using ProofAgent.Llm;

namespace ProofAgent.Agent;

public record CoqProofRun(
    bool Success,
    CoqError? LastError,
    string LastAssistantText,
    LlmUsage TotalLlmUsage,
    bool ExceededMaxToolRounds = false);
