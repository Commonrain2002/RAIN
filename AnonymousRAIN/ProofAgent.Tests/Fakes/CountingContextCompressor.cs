using ProofAgent.Llm;
using ProofAgent.Session;

namespace ProofAgent.Tests.Fakes;

public class CountingContextCompressor : IContextCompressor
{
    private readonly IContextCompressor _Inner;

    public CountingContextCompressor(IContextCompressor inner)
    {
        _Inner = inner;
    }

    public int CompressCallCount { get; private set; }

    public IReadOnlyList<LlmMessage> Compress(IReadOnlyList<LlmMessage> messages)
    {
        CompressCallCount++;
        return _Inner.Compress(messages);
    }
}
