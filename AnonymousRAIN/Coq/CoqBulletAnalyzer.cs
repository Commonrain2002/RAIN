using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Coq;

/// <summary>Backward and forward bullet-spine analysis from parse_sentence classifications.</summary>
public class CoqBulletAnalyzer
{
    #region Fields

    private const string _RootBracePopFailureReasonInvariant =
        "Closing '}' would pop the synthetic root brace at stack[0].";

    private readonly ILogger _Logger;

    private readonly ICoqSentenceSplitter _SentenceSplitter;

    private readonly ICoqSentenceAnalyzer _SentenceAnalyzer;

    #endregion Fields

    public CoqBulletAnalyzer(
        ILogger logger,
        ICoqSentenceSplitter sentenceSplitter,
        ICoqSentenceAnalyzer sentenceAnalyzer)
    {
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _SentenceSplitter = sentenceSplitter ?? throw new ArgumentNullException(nameof(sentenceSplitter));
        _SentenceAnalyzer = sentenceAnalyzer ?? throw new ArgumentNullException(nameof(sentenceAnalyzer));
    }

    public async Task<CoqBulletStackGetResult> GetBulletStackAsync(
        RelativePath relativeCoqFilePath,
        int lineOneBased,
        int columnZeroBased,
        CancellationToken cancellationToken)
    {
        if (relativeCoqFilePath == null)
        {
            return _StackFail("relativeCoqFilePath is null.");
        }

        var sentences = await _SentenceSplitter
            .SplitAsync(relativeCoqFilePath, cancellationToken)
            .ConfigureAwait(false);
        if (sentences.Count == 0)
        {
            _Logger.Information(
                "coq_bullet_analyzer: parse-sentence-script returned no sentences for {File}.",
                relativeCoqFilePath);
            return _StackFail("parse-sentence-script returned no sentences.");
        }

        return await _TryGetBulletStackAsync(
                relativeCoqFilePath,
                sentences,
                lineOneBased,
                columnZeroBased,
                cancellationToken)
            .ConfigureAwait(false);
    }

    public async Task<CoqBulletEnd> GetBulletEndAsync(
        RelativePath relativeCoqFilePath,
        int lineOneBased,
        int columnZeroBased,
        CancellationToken cancellationToken)
    {
        if (relativeCoqFilePath == null)
        {
            return _EndFail("relativeCoqFilePath is null.");
        }

        var sentences = await _SentenceSplitter
            .SplitAsync(relativeCoqFilePath, cancellationToken)
            .ConfigureAwait(false);
        if (sentences.Count == 0)
        {
            _Logger.Information(
                "coq_bullet_analyzer: parse-sentence-script returned no sentences for {File}.",
                relativeCoqFilePath);
            return _EndFail("parse-sentence-script returned no sentences.");
        }

        return await _GetBulletEndAsync(
                relativeCoqFilePath,
                sentences,
                lineOneBased,
                columnZeroBased,
                cancellationToken)
            .ConfigureAwait(false);
    }

    #region Private Methods

    private async Task<CoqBulletStackGetResult> _TryGetBulletStackAsync(
        RelativePath relativeCoqFilePath,
        IReadOnlyList<CoqSentence> sentences,
        int lineOneBased,
        int columnZeroBased,
        CancellationToken cancellationToken)
    {
        var preparation = await _PrepareAnchorIndexAsync(
                relativeCoqFilePath,
                sentences,
                lineOneBased,
                columnZeroBased,
                cancellationToken)
            .ConfigureAwait(false);
        if (!string.IsNullOrEmpty(preparation.FailureReason))
        {
            return _StackFail(preparation.FailureReason);
        }

        var sortedSentences = preparation.SortedSentences;
        var anchorSentenceIndex = preparation.AnchorSentenceIndex;
        if (!_TryGetBackwardBulletStack(
                sortedSentences,
                anchorSentenceIndex,
                out var backwardStack))
        {
            return _StackFail(_RootBracePopFailureReasonInvariant);
        }

        if (backwardStack.GetTopCellIdentity() == null)
        {
            return _StackFail("Bullet stack is empty before error sentence; cannot determine bullet spine.");
        }

        return CoqBulletStackGetResult.FromSuccess(backwardStack.ToSnapshot());
    }

    private async Task<CoqBulletAnchorPreparation> _PrepareAnchorIndexAsync(
        RelativePath relativeCoqFilePath,
        IReadOnlyList<CoqSentence> sentences,
        int lineOneBased,
        int columnZeroBased,
        CancellationToken cancellationToken)
    {
        if (sentences.Count == 0)
        {
            return CoqBulletAnchorPreparation.FromFailure("sentences is empty.");
        }

        var sortedSentences = sentences.OrderBy(static s => s.Index).ToList();
        var sentenceAtPosition = await _SentenceAnalyzer
            .GetSentenceAtPositionAsync(relativeCoqFilePath, lineOneBased, columnZeroBased, cancellationToken)
            .ConfigureAwait(false);
        if (sentenceAtPosition == null)
        {
            return CoqBulletAnchorPreparation.FromFailure("Could not map position to a sentence list index.");
        }

        var anchorSentenceIndex = sortedSentences.FindIndex(sentence => sentence.Index == sentenceAtPosition.Index);
        if (anchorSentenceIndex < 0)
        {
            return CoqBulletAnchorPreparation.FromFailure("Could not map position to a sentence list index.");
        }

        return CoqBulletAnchorPreparation.FromSuccess(sortedSentences, anchorSentenceIndex);
    }

    private bool _TryGetBackwardBulletStack(
        List<CoqSentence> sortedSentences,
        int anchorSentenceIndex,
        out CoqBulletStack stackResult)
    {
        var stack = CoqBulletStack.CreateForBackwardBuild();

        for (var i = 0; i < anchorSentenceIndex; i++)
        {
            if (!stack.ApplySentence(sortedSentences[i]))
            {
                stackResult = stack;
                return false;
            }
        }

        stackResult = stack;
        return true;
    }

    private CoqBulletStackGetResult _StackFail(string reason)
    {
        _Logger.Information("coq_bullet_analyzer: {Reason}", reason);
        return CoqBulletStackGetResult.FromFailure(reason);
    }

    private async Task<CoqBulletEnd> _GetBulletEndAsync(
        RelativePath relativeCoqFilePath,
        IReadOnlyList<CoqSentence> sentences,
        int lineOneBased,
        int columnZeroBased,
        CancellationToken cancellationToken)
    {
        var preparation = await _PrepareAnchorIndexAsync(
                relativeCoqFilePath,
                sentences,
                lineOneBased,
                columnZeroBased,
                cancellationToken)
            .ConfigureAwait(false);
        if (!string.IsNullOrEmpty(preparation.FailureReason))
        {
            return _EndFail(preparation.FailureReason);
        }

        var sortedSentences = preparation.SortedSentences;
        var anchorSentenceIndex = preparation.AnchorSentenceIndex;
        if (!_TryGetBackwardBulletStack(
                sortedSentences,
                anchorSentenceIndex,
                out var backwardStack))
        {
            return _EndFail(_RootBracePopFailureReasonInvariant);
        }

        var backwardTopID = backwardStack.GetTopCellIdentity();
        if (backwardTopID == null)
        {
            return _EndFail("Bullet stack is empty before error sentence; cannot determine bullet spine.");
        }

        var backwardTopCellID = backwardTopID.Value;
        var forwardBoundary = _ScanForwardBoundary(
            sortedSentences,
            anchorSentenceIndex,
            backwardStack,
            backwardTopCellID);
        if (!forwardBoundary.Succeeded)
        {
            return _EndFail(forwardBoundary.FailureReason);
        }

        var lastListIndex = forwardBoundary.BoundaryUpper - 1;
        if (lastListIndex < anchorSentenceIndex)
        {
            return _EndFail("Bullet boundary sits before error sentence (no lines to comment).");
        }

        var lastSentence = sortedSentences[lastListIndex];
        return new CoqBulletEnd(
            true,
            "",
            anchorSentenceIndex,
            lastSentence.EndLineOneBased,
            lastSentence.EndColumnZeroBased,
            lastListIndex);
    }

    private CoqBulletForwardBoundary _ScanForwardBoundary(
        List<CoqSentence> sortedSentences,
        int anchorSentenceIndex,
        CoqBulletStack backwardStack,
        ulong backwardTopCellID)
    {
        var forwardStack = backwardStack.Clone();
        var boundaryUpper = sortedSentences.Count;

        for (var i = anchorSentenceIndex; i < sortedSentences.Count; i++)
        {
            var sentence = sortedSentences[i];
            var classification = sentence.Classification;
            if (!_IsProofStepClassification(classification))
            {
                var reason =
                    $"coq_bullet_analyzer: sentence index={sentence.Index} has classification {classification} that is not a proof step.";
                _Logger.Information(reason);
                return CoqBulletForwardBoundary.FromFailure(reason);
            }

            if (!forwardStack.ApplySentence(sentence))
            {
                return CoqBulletForwardBoundary.FromFailure(_RootBracePopFailureReasonInvariant);
            }

            if (!forwardStack.CheckCellIDInStack(backwardTopCellID))
            {
                boundaryUpper = i;
                break;
            }
        }

        return CoqBulletForwardBoundary.FromBoundary(boundaryUpper);
    }

    private static bool _IsProofStepClassification(CoqSentenceClassification classification)
    {
        return classification is CoqSentenceClassification.Step
            or CoqSentenceClassification.Bullet
            or CoqSentenceClassification.Curly;
    }

    private CoqBulletEnd _EndFail(string reason)
    {
        _Logger.Information("coq_bullet_analyzer: {Reason}", reason);
        return new CoqBulletEnd(false, reason, -1, 0, 0, -1);
    }

    #endregion Private Methods

    #region Nested Types

    private class CoqBulletAnchorPreparation
    {
        private CoqBulletAnchorPreparation(
            string failureReason,
            List<CoqSentence> sortedSentences,
            int anchorSentenceIndex)
        {
            FailureReason = failureReason;
            SortedSentences = sortedSentences;
            AnchorSentenceIndex = anchorSentenceIndex;
        }

        public string FailureReason { get; }

        public List<CoqSentence> SortedSentences { get; }

        public int AnchorSentenceIndex { get; }

        public static CoqBulletAnchorPreparation FromFailure(string failureReason)
        {
            return new CoqBulletAnchorPreparation(failureReason, [], default);
        }

        public static CoqBulletAnchorPreparation FromSuccess(
            List<CoqSentence> sortedSentences,
            int anchorSentenceIndex)
        {
            return new CoqBulletAnchorPreparation("", sortedSentences, anchorSentenceIndex);
        }
    }

    private readonly struct CoqBulletForwardBoundary
    {
        private CoqBulletForwardBoundary(
            bool succeeded,
            int boundaryUpper,
            string failureReason)
        {
            Succeeded = succeeded;
            BoundaryUpper = boundaryUpper;
            FailureReason = failureReason;
        }

        public bool Succeeded { get; }

        public int BoundaryUpper { get; }

        public string FailureReason { get; }

        public static CoqBulletForwardBoundary FromFailure(string failureReason)
        {
            return new CoqBulletForwardBoundary(false, default, failureReason);
        }

        public static CoqBulletForwardBoundary FromBoundary(int boundaryUpper)
        {
            return new CoqBulletForwardBoundary(true, boundaryUpper, "");
        }
    }

    #endregion Nested Types
}
