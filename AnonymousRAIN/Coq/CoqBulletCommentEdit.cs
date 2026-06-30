namespace ProofAgent.Coq;

/// <summary>Outcome of bullet-range planning for commenting out a failing proof spine.</summary>
public record CoqBulletCommentEdit(
    bool Succeeded,
    string FailureReason,
    string[] CommentEditLines);
