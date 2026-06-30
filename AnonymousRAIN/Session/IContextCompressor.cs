using ProofAgent.Llm;

namespace ProofAgent.Session;

public interface IContextCompressor
{
    IReadOnlyList<LlmMessage> Compress(IReadOnlyList<LlmMessage> messages);
}
