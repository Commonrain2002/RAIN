using System.Text.Json;
using System.Text.Json.Serialization;

namespace ProofAgent.Coq;

public class CoqSentenceClassificationJsonConverter : JsonConverter<CoqSentenceClassification>
{
    private const string _VtProofStepBulletPrefix = "VtProofStep(bullet)";

    private const string _VtProofStepCurlyPrefix = "VtProofStep(curly)";

    private const string _VtProofStepPrefix = "VtProofStep";

    public override CoqSentenceClassification Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.Null)
        {
            return CoqSentenceClassification.Others;
        }

        if (reader.TokenType != JsonTokenType.String)
        {
            throw new JsonException("Expected string for CoqSentence classification.");
        }

        return _ParseFromCoqStoqTag(reader.GetString());
    }

    public override void Write(
        Utf8JsonWriter writer,
        CoqSentenceClassification value,
        JsonSerializerOptions options)
    {
        writer.WriteStringValue(_ToCoqStoqTag(value));
    }

    private static CoqSentenceClassification _ParseFromCoqStoqTag(string? raw)
    {
        var trimmed = (raw ?? "").Trim();
        if (trimmed.Length == 0)
        {
            return CoqSentenceClassification.Others;
        }

        if (trimmed.StartsWith(_VtProofStepBulletPrefix, StringComparison.Ordinal))
        {
            return CoqSentenceClassification.Bullet;
        }

        if (trimmed.StartsWith(_VtProofStepCurlyPrefix, StringComparison.Ordinal))
        {
            return CoqSentenceClassification.Curly;
        }

        if (trimmed.StartsWith(_VtProofStepPrefix, StringComparison.Ordinal))
        {
            return CoqSentenceClassification.Step;
        }

        return CoqSentenceClassification.Others;
    }

    private static string _ToCoqStoqTag(CoqSentenceClassification value)
    {
        return value switch
        {
            CoqSentenceClassification.Bullet => "VtProofStep(bullet)",
            CoqSentenceClassification.Curly => "VtProofStep(curly)",
            CoqSentenceClassification.Step => "VtProofStep",
            _ => ""
        };
    }
}
