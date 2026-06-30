using System.Text.Json;
using ProofAgent.Coq;
using Xunit;

namespace ProofAgent.Tests;

public class CoqSentenceClassificationIngestTests
{
    private static readonly JsonSerializerOptions _JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true
    };

    [Theory]
    [InlineData("VtProofStep(bullet)", CoqSentenceClassification.Bullet)]
    [InlineData("VtProofStep(bullet)extra", CoqSentenceClassification.Bullet)]
    [InlineData("VtProofStep(curly)", CoqSentenceClassification.Curly)]
    [InlineData("  VtProofStep(curly)  ", CoqSentenceClassification.Curly)]
    [InlineData("VtProofStep", CoqSentenceClassification.Step)]
    [InlineData("  VtProofStep  ", CoqSentenceClassification.Step)]
    [InlineData("VtStartProof(GuaranteesOpacity,[u])", CoqSentenceClassification.Others)]
    [InlineData("VtSideff([x],VtLater)", CoqSentenceClassification.Others)]
    [InlineData("VtQed(VtKeep(VtKeepAxiom))", CoqSentenceClassification.Others)]
    [InlineData("", CoqSentenceClassification.Others)]
    public void JsonIngest_MapsCoqStoqClassificationToEnum(string coqStoqTag, CoqSentenceClassification expected)
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
        var sentence = JsonSerializer.Deserialize<CoqSentence>(json, _JsonOptions)!;
        Assert.Equal(expected, sentence.Classification);
    }
}
