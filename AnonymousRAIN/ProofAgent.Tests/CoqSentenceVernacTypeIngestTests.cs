using System.Text.Json;
using ProofAgent.Coq;
using Xunit;

namespace ProofAgent.Tests;

public class CoqSentenceVernacTypeIngestTests
{
    private static readonly JsonSerializerOptions _JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true
    };

    [Theory]
    [InlineData("definition", CoqSentenceVernacType.Definition)]
    [InlineData("Definition", CoqSentenceVernacType.Definition)]
    [InlineData("  fixpoint  ", CoqSentenceVernacType.Fixpoint)]
    [InlineData("inductive", CoqSentenceVernacType.Inductive)]
    [InlineData("theorem", CoqSentenceVernacType.Theorem)]
    [InlineData("require", CoqSentenceVernacType.Require)]
    [InlineData("notation", CoqSentenceVernacType.Other)]
    [InlineData("other", CoqSentenceVernacType.Other)]
    [InlineData("", CoqSentenceVernacType.Other)]
    public void JsonIngest_MapsVernacTypeToEnum(string vernacTypeTag, CoqSentenceVernacType expected)
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
                "vernac_type": {{JsonSerializer.Serialize(vernacTypeTag)}}
              }
              """;
        var sentence = JsonSerializer.Deserialize<CoqSentence>(json, _JsonOptions)!;
        Assert.Equal(expected, sentence.VernacType);
    }
}
