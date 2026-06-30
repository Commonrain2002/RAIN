using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Coq;

/// <summary>Chooses bullet-spine sentence ranges and wraps them in one <c>(* ... *) all: admit.</c> block without changing line count.</summary>
public class CoqProofBulletIterationPlanner
{
    #region Fields

    private readonly ILogger _Logger;

    private readonly CoqBulletAnalyzer _BulletAnalyzer;

    private readonly ICoqSentenceSplitter _SentenceSplitter;

    #endregion Fields

    public CoqProofBulletIterationPlanner(
        ILogger logger,
        CoqBulletAnalyzer bulletAnalyzer,
        ICoqSentenceSplitter sentenceSplitter)
    {
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _BulletAnalyzer = bulletAnalyzer ?? throw new ArgumentNullException(nameof(bulletAnalyzer));
        _SentenceSplitter = sentenceSplitter ?? throw new ArgumentNullException(nameof(sentenceSplitter));
    }

    /// <summary>Mutates proof lines for one comment step without writing disk. On-disk file at relativeCoqFilePath must match workingLines.</summary>
    public async Task<CoqBulletCommentEdit> PlanEditAsync(
        RelativePath relativeCoqFilePath,
        string[] workingLines,
        CoqError error,
        CancellationToken cancellationToken)
    {
        var validateFailure = _ValidateNonEmptyLines(
            relativeCoqFilePath,
            workingLines);
        if (validateFailure != null)
        {
            return validateFailure;
        }

        var sentences = await _SentenceSplitter
            .SplitAsync(relativeCoqFilePath, cancellationToken)
            .ConfigureAwait(false);
        if (sentences.Count == 0)
        {
            _Logger.Information(
                "bullet_iteration_planner: parse-sentence-script returned no sentences for {File}.",
                relativeCoqFilePath);
            return _Fail("parse-sentence-script returned no sentences.");
        }

        var bulletEnd = await _BulletAnalyzer
            .GetBulletEndAsync(
                relativeCoqFilePath,
                error.Line,
                error.Column,
                cancellationToken)
            .ConfigureAwait(false);
        if (!bulletEnd.Succeeded)
        {
            return _Fail(string.IsNullOrEmpty(bulletEnd.FailureReason)
                ? "Bullet end analysis failed."
                : bulletEnd.FailureReason);
        }

        var sortedsentences = sentences.OrderBy(static s => s.Index).ToList();
        return _BuildResult(
            workingLines,
            sortedsentences,
            bulletEnd.AnchorSentenceIndex,
            bulletEnd.LastSentenceIndex);
    }

    #region Private Methods

    private CoqBulletCommentEdit _Fail(string reason)
    {
        _Logger.Information("bullet_iteration_planner: {Reason}", reason);
        return new CoqBulletCommentEdit(false, reason, Array.Empty<string>());
    }

    private CoqBulletCommentEdit? _ValidateNonEmptyLines(
        RelativePath relativeCoqFilePath,
        string[] workingLines)
    {
        if (relativeCoqFilePath == null)
        {
            return _Fail("relativeCoqFilePath is null.");
        }

        if (workingLines.Length == 0)
        {
            return _Fail("workingLines is empty.");
        }

        return null;
    }

    private CoqBulletCommentEdit _BuildResult(
        string[] workingLines,
        List<CoqSentence> sortedSentences,
        int anchorIndex,
        int lastIndex)
    {
        if (lastIndex < anchorIndex)
        {
            return _Fail("Bullet boundary sits before error sentence (no lines to comment).");
        }

        if (!_BuildCommentEditLines(workingLines, sortedSentences, anchorIndex, lastIndex, out var lines))
        {
            return _Fail("Could not resolve block comment insert bounds for bullet sentence span.");
        }

        return new CoqBulletCommentEdit(true, "", lines);
    }

    private static bool _BuildCommentEditLines(
        string[] workingLines,
        List<CoqSentence> sortedSentences,
        int firstIndex,
        int lastIndex,
        out string[] lines)
    {
        lines = (string[])workingLines.Clone();
        var firstSentence = sortedSentences[firstIndex];
        var lastSentence = sortedSentences[lastIndex];
        if (!_TryGetBlockCommentInsertBounds(workingLines, firstSentence, lastSentence, out var insertBounds))
        {
            return false;
        }

        _ApplyBlockCommentEdit(lines, workingLines, insertBounds);
        return true;
    }

    private static bool _TryGetBlockCommentInsertBounds(
        string[] workingLines,
        CoqSentence firstSentence,
        CoqSentence lastSentence,
        out CoqBlockCommentInsertBounds insertBounds)
    {
        insertBounds = default;

        var firstLineOneBased = firstSentence.StartLineOneBased;
        var lastLineOneBased = lastSentence.EndLineOneBased;
        if (firstLineOneBased <= 0 || lastLineOneBased < firstLineOneBased)
        {
            return false;
        }

        var firstLineIndex = firstLineOneBased - 1;
        var lastLineIndex = lastLineOneBased - 1;
        if (firstLineIndex < 0
            || firstLineIndex >= workingLines.Length
            || lastLineIndex < 0
            || lastLineIndex >= workingLines.Length)
        {
            return false;
        }

        var firstLineLen = workingLines[firstLineIndex].Length;
        var startCol = _ClampStart(firstSentence.StartColumnZeroBased, firstLineLen);

        var lastLineLen = workingLines[lastLineIndex].Length;
        var endCol = _ClampEnd(lastSentence.EndColumnZeroBased, 0, lastLineLen);

        if (firstLineIndex == lastLineIndex && endCol <= startCol)
        {
            return false;
        }

        insertBounds = new CoqBlockCommentInsertBounds(firstLineIndex, lastLineIndex, startCol, endCol);
        return true;
    }

    private static int _ClampStart(int col, int lineLen)
    {
        if (col < 0)
        {
            return 0;
        }

        if (col > lineLen)
        {
            return lineLen;
        }

        return col;
    }

    private static int _ClampEnd(int endCol, int startCol, int lineLen)
    {
        if (endCol < startCol)
        {
            return startCol;
        }

        if (endCol > lineLen)
        {
            return lineLen;
        }

        return endCol;
    }

    private static void _ApplyBlockCommentEdit(
        string[] linesToBeEdited,
        string[] workingLines,
        CoqBlockCommentInsertBounds insertBounds)
    {
        const string openPrefix = "(*";
        const string closeSuffix = "*) all: admit.";

        if (insertBounds.FirstLineIndex == insertBounds.LastLineIndex)
        {
            var line = linesToBeEdited[insertBounds.FirstLineIndex];
            // Close before open so indices stay tied to the original line (no column drift).
            line = line.Insert(insertBounds.EndCol, closeSuffix);
            line = line.Insert(insertBounds.StartCol, openPrefix);
            linesToBeEdited[insertBounds.FirstLineIndex] = line;
            return;
        }

        linesToBeEdited[insertBounds.LastLineIndex] = workingLines[insertBounds.LastLineIndex].Insert(insertBounds.EndCol, closeSuffix);
        linesToBeEdited[insertBounds.FirstLineIndex] = workingLines[insertBounds.FirstLineIndex].Insert(insertBounds.StartCol, openPrefix);
    }

    #endregion Private Methods

    #region Nested Types

    private readonly struct CoqBlockCommentInsertBounds
    {
        public CoqBlockCommentInsertBounds(
            int firstLineIndex,
            int lastLineIndex,
            int startCol,
            int endCol)
        {
            FirstLineIndex = firstLineIndex;
            LastLineIndex = lastLineIndex;
            StartCol = startCol;
            EndCol = endCol;
        }

        public int FirstLineIndex { get; }

        public int LastLineIndex { get; }

        public int StartCol { get; }

        public int EndCol { get; }
    }

    #endregion Nested Types
}
