using System.Linq;
using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Coq;

/// <summary>Maps file line/column to <see cref="CoqSentence"/> using parse-sentence-script sentence spans.</summary>
public class CoqSentenceAnalyzer : ICoqSentenceAnalyzer
{
    #region Fields

    private readonly ILogger _Logger;

    private readonly ICoqSentenceSplitter _SentenceSplitter;

    #endregion Fields

    public CoqSentenceAnalyzer(
        ILogger logger,
        ICoqSentenceSplitter sentenceSplitter)
    {
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _SentenceSplitter = sentenceSplitter ?? throw new ArgumentNullException(nameof(sentenceSplitter));
    }

    public Task<CoqSentence?> GetSentenceBeforeAsync(
        RelativePath relativeCoqFilePath,
        int lineOneBased,
        int columnZeroBased,
        CancellationToken cancellationToken)
    {
        return _GetSentenceAsync(
            relativeCoqFilePath,
            lineOneBased,
            columnZeroBased,
            SentencePositionLookupKind.Before,
            cancellationToken);
    }

    public Task<CoqSentence?> GetSentenceAtPositionAsync(
        RelativePath relativeCoqFilePath,
        int lineOneBased,
        int columnZeroBased,
        CancellationToken cancellationToken)
    {
        return _GetSentenceAsync(
            relativeCoqFilePath,
            lineOneBased,
            columnZeroBased,
            SentencePositionLookupKind.At,
            cancellationToken);
    }

    #region Private Methods

    private async Task<CoqSentence?> _GetSentenceAsync(
        RelativePath relativeCoqFilePath,
        int lineOneBased,
        int columnZeroBased,
        SentencePositionLookupKind lookupKind,
        CancellationToken cancellationToken)
    {
        _ValidatePositionInputs(relativeCoqFilePath, lineOneBased, columnZeroBased);

        var sentences = await _SentenceSplitter
            .SplitAsync(relativeCoqFilePath, cancellationToken)
            .ConfigureAwait(false);
        if (sentences.Count == 0)
        {
            _Logger.Information(
                "coq_sentence_analyzer: parse-sentence-script returned no sentences for {File}.",
                relativeCoqFilePath);
            return null;
        }

        if (lookupKind == SentencePositionLookupKind.Before)
        {
            return _SelectLastSentenceEndingBeforeCursor(
                sentences,
                lineOneBased,
                columnZeroBased);
        }

        return _SelectSentenceContainingCursor(
            sentences,
            lineOneBased,
            columnZeroBased);
    }

    private static void _ValidatePositionInputs(
        RelativePath relativeCoqFilePath,
        int lineOneBased,
        int columnZeroBased)
    {
        if (relativeCoqFilePath == null)
        {
            throw new ArgumentNullException(nameof(relativeCoqFilePath));
        }

        if (lineOneBased <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(lineOneBased), "lineOneBased must be a positive integer.");
        }

        if (columnZeroBased < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(columnZeroBased), "columnZeroBased must be non-negative.");
        }
    }

    private static CoqSentence? _SelectLastSentenceEndingBeforeCursor(
        IReadOnlyList<CoqSentence> sentences,
        int lineOneBased,
        int columnZeroBased)
    {
        CoqSentence? selected = null;
        foreach (var sentence in sentences.OrderBy(static candidate => candidate.Index))
        {
            if (_CompareLineColumn(
                    sentence.EndLineOneBased,
                    sentence.EndColumnZeroBased,
                    lineOneBased,
                    columnZeroBased) < 0)
            {
                selected = sentence;
            }
        }

        return selected;
    }

    private CoqSentence? _SelectSentenceContainingCursor(
        IReadOnlyList<CoqSentence> sentences,
        int lineOneBased,
        int columnZeroBased)
    {
        var selectedSentence = sentences
            .Where(candidate => _ContainsCursor(candidate, lineOneBased, columnZeroBased))
            .OrderByDescending(static sentence => sentence.Index)
            .FirstOrDefault();

        if (selectedSentence == null)
        {
            _Logger.Information(
                "coq_sentence_analyzer: no sentence contains line {Line} column {Column}.",
                lineOneBased,
                columnZeroBased);
            return null;
        }

        return selectedSentence;
    }

    private static bool _ContainsCursor(
        CoqSentence sentence,
        int lineOneBased,
        int columnZeroBased)
    {
        if (_CompareLineColumn(
                lineOneBased,
                columnZeroBased,
                sentence.StartLineOneBased,
                sentence.StartColumnZeroBased) < 0)
        {
            return false;
        }

        if (_CompareLineColumn(
                lineOneBased,
                columnZeroBased,
                sentence.EndLineOneBased,
                sentence.EndColumnZeroBased) >= 0)
        {
            return false;
        }

        return true;
    }

    private static int _CompareLineColumn(int lineA, int columnA, int lineB, int columnB)
    {
        if (lineA != lineB)
        {
            return lineA.CompareTo(lineB);
        }

        return columnA.CompareTo(columnB);
    }

    #endregion Private Methods

    #region Nested Types

    private enum SentencePositionLookupKind
    {
        Before,

        At
    }

    #endregion Nested Types
}
