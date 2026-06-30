namespace ProofAgent.Agent;

public interface IPromptTextSource
{
    string GetText(string relativePath);
}
