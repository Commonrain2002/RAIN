using System.Text.Json;
using ProofAgent.Coq;
using Xunit;

namespace ProofAgent.Tests;

public class CoqSentenceClassificationJsonTests
{
    [Fact]
    public void CoqSentenceRecord_Deserializes_Classification_FromJsonCaseInsensitiveProperty()
    {
        const string jsonSnippet =
            """
            {
              "index": 16,
              "byte_start": 401,
              "byte_end": 402,
              "start_line": 17,
              "start_column": 16,
              "end_line": 17,
              "end_column": 17,
              "classification": "VtProofStep(bullet)",
              "text": "-"
            }
            """;

        var deserialized = JsonSerializer.Deserialize<CoqSentence>(
            jsonSnippet,
            new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true,
                ReadCommentHandling = JsonCommentHandling.Skip,
                AllowTrailingCommas = true
            })!;

        Assert.Equal(CoqSentenceClassification.Bullet, deserialized.Classification);
        Assert.Equal("-", deserialized.Text.Trim());
        Assert.Equal(16, deserialized.Index);
    }

    [Fact]
    public void CoqSentenceRecord_Deserializes_VernacTypeNameAndTokens()
    {
        const string jsonSnippet =
            """
            {
              "index": 5,
              "start_line": 17,
              "start_column": 0,
              "end_line": 17,
              "end_column": 45,
              "classification": "VtStartProof(GuaranteesOpacity,[test])",
              "vernac_type": "theorem",
              "name": "test",
              "tokens": ["Lemma", "test", ":", "forall", "x", "y", ":", "nat", ",", "x", "+", "y", "=", "y", "+", "x", "."],
              "text": "Lemma test : forall x y : nat, x + y = y + x."
            }
            """;

        var deserialized = JsonSerializer.Deserialize<CoqSentence>(
            jsonSnippet,
            new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true,
                ReadCommentHandling = JsonCommentHandling.Skip,
                AllowTrailingCommas = true
            })!;

        Assert.Equal(CoqSentenceVernacType.Theorem, deserialized.VernacType);
        Assert.Equal("test", deserialized.Name);
        Assert.Equal(
            new[] { "Lemma", "test", ":", "forall", "x", "y", ":", "nat", ",", "x", "+", "y", "=", "y", "+", "x", "." },
            deserialized.Tokens);
    }
}
