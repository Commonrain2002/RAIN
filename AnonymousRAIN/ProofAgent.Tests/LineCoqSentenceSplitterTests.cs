using ProofAgent.Coq;
using ProofAgent.Tools;

namespace ProofAgent.Tests;

/// <summary>
/// Test-only splitter: one logical sentence per physical line (joined with <see cref="Environment.NewLine"/>),
/// matching <see cref="CoqEnvironmentCapturer"/> joined-source line/column model.
/// </summary>
public class LineCoqSentenceSplitterTests : ICoqSentenceSplitter
{
    private readonly ProjectFileSystem _FileSystem;

    public LineCoqSentenceSplitterTests(ProjectFileSystem fileSystem)
    {
        _FileSystem = fileSystem ?? throw new ArgumentNullException(nameof(fileSystem));
    }

    public Task<IReadOnlyList<CoqSentence>> SplitAsync(RelativePath relativeCoqFilePath, CancellationToken cancellationToken)
    {
        _ = cancellationToken;
        if (relativeCoqFilePath == null || !_FileSystem.Exists(relativeCoqFilePath))
        {
            return Task.FromResult<IReadOnlyList<CoqSentence>>(Array.Empty<CoqSentence>());
        }

        var lines = _FileSystem.ReadAllLines(relativeCoqFilePath);
        if (lines.Length == 0)
        {
            return Task.FromResult<IReadOnlyList<CoqSentence>>(Array.Empty<CoqSentence>());
        }

        var list = new List<CoqSentence>();
        for (var i = 0; i < lines.Length; i++)
        {
            var line = lines[i];
            var startColumn = _StartColumnIgnoringIndent(line);

            list.Add(new CoqSentence
            {
                Index = i,
                StartLineOneBased = i + 1,
                StartColumnZeroBased = startColumn,
                EndLineOneBased = i + 1,
                EndColumnZeroBased = line.Length,
                Text = line,
            });
        }

        return Task.FromResult<IReadOnlyList<CoqSentence>>(list);
    }

    private static int _StartColumnIgnoringIndent(string line)
    {
        var j = 0;
        while (j < line.Length && line[j] is ' ' or '\t')
        {
            j++;
        }

        return j;
    }
}
