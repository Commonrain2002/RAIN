using System.Text.Json;
using System.Text.Json.Serialization;

namespace ProofAgent.Coq;

public class CoqSentenceVernacTypeJsonConverter : JsonConverter<CoqSentenceVernacType>
{
    public override CoqSentenceVernacType Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.Null)
        {
            return CoqSentenceVernacType.Other;
        }

        if (reader.TokenType != JsonTokenType.String)
        {
            throw new JsonException("Expected string for CoqSentence vernac_type.");
        }

        return _ParseFromScriptTag(reader.GetString());
    }

    public override void Write(
        Utf8JsonWriter writer,
        CoqSentenceVernacType value,
        JsonSerializerOptions options)
    {
        writer.WriteStringValue(_ToScriptTag(value));
    }

    private static CoqSentenceVernacType _ParseFromScriptTag(string? raw)
    {
        var trimmed = (raw ?? "").Trim();
        if (trimmed.Length == 0)
        {
            return CoqSentenceVernacType.Other;
        }

        if (string.Equals(trimmed, "definition", StringComparison.OrdinalIgnoreCase))
        {
            return CoqSentenceVernacType.Definition;
        }

        if (string.Equals(trimmed, "fixpoint", StringComparison.OrdinalIgnoreCase))
        {
            return CoqSentenceVernacType.Fixpoint;
        }

        if (string.Equals(trimmed, "inductive", StringComparison.OrdinalIgnoreCase))
        {
            return CoqSentenceVernacType.Inductive;
        }

        if (string.Equals(trimmed, "theorem", StringComparison.OrdinalIgnoreCase))
        {
            return CoqSentenceVernacType.Theorem;
        }

        if (string.Equals(trimmed, "require", StringComparison.OrdinalIgnoreCase))
        {
            return CoqSentenceVernacType.Require;
        }

        return CoqSentenceVernacType.Other;
    }

    private static string _ToScriptTag(CoqSentenceVernacType value)
    {
        return value switch
        {
            CoqSentenceVernacType.Definition => "definition",
            CoqSentenceVernacType.Fixpoint => "fixpoint",
            CoqSentenceVernacType.Inductive => "inductive",
            CoqSentenceVernacType.Theorem => "theorem",
            CoqSentenceVernacType.Require => "require",
            _ => "other"
        };
    }
}
