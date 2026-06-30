using System.Text.Json;
using ProofAgent.Coq;

namespace ProofAgent.Tests;

public static class CoqLineAlignedSentenceTestHelper
{
    private static readonly JsonSerializerOptions _SentenceJsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true
    };

    public static List<CoqSentence> SentencesLineAlignedOnePerPhysicalLine(
        string[] lines,
        string[] classificationByAscendingIndexExclusive)
    {
        if (lines.Length != classificationByAscendingIndexExclusive.Length)
        {
            throw new ArgumentException("lines and classifications must align by count.");
        }

        var accumulatorSentencesBuilt = new List<CoqSentence>();

        for (var logicalLineIndexInclusiveZeroBased = 0;
             logicalLineIndexInclusiveZeroBased < lines.Length;
             logicalLineIndexInclusiveZeroBased++)
        {
            var physicalLineSliceTextOriginal = lines[logicalLineIndexInclusiveZeroBased];
            var startColumnSkippingIndent = StartColumnSkippingIndent(physicalLineSliceTextOriginal);

            accumulatorSentencesBuilt.Add(
                new CoqSentence
                {
                    Index = logicalLineIndexInclusiveZeroBased,
                    StartLineOneBased = logicalLineIndexInclusiveZeroBased + 1,
                    StartColumnZeroBased = startColumnSkippingIndent,
                    EndLineOneBased = logicalLineIndexInclusiveZeroBased + 1,
                    EndColumnZeroBased = physicalLineSliceTextOriginal.Length,
                    Text = physicalLineSliceTextOriginal,
                    Classification = _ClassificationFromCoqStoqJsonTag(
                        classificationByAscendingIndexExclusive[logicalLineIndexInclusiveZeroBased])
                });
        }

        return accumulatorSentencesBuilt;
    }

    private static CoqSentenceClassification _ClassificationFromCoqStoqJsonTag(string coqStoqTag)
    {
        var json =
            $$"""
              {
                "index": 0,
                "start_line": 1,
                "start_column": 0,
                "end_line": 1,
                "end_column": 0,
                "text": "x",
                "classification": {{JsonSerializer.Serialize(coqStoqTag)}}
              }
              """;
        var sentence = JsonSerializer.Deserialize<CoqSentence>(json, _SentenceJsonOptions)
            ?? throw new InvalidOperationException("Failed to deserialize test CoqSentence for classification.");
        return sentence.Classification;
    }

    private static int StartColumnSkippingIndent(string lineText)
    {
        var columnCursor = 0;
        while (columnCursor < lineText.Length && lineText[columnCursor] is ' ' or '\t')
        {
            columnCursor++;
        }

        return columnCursor;
    }
}
