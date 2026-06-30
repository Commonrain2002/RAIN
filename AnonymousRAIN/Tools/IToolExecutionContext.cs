using System.Text.RegularExpressions;

namespace ProofAgent.Tools;

public interface IToolExecutionContext
{
    void Replace(string path, string oldText, string newText);

    string ReadFileRange(string path, int startLine, int endLine);

    string ReadExtraFileRange(string path, int startLine, int endLine);

    string SearchByRegex(Regex regex, int offset, int maxMatches, bool showContext);

    string ReadLemmasInFile(string path, int offset, int maxMatches);

    string SearchExtraByRegex(Regex regex, int offset, int maxMatches, bool showContext);

    Task<string> RunMultiErrorCheckAsync(CancellationToken cancellationToken);
}
