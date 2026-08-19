using System.Text;

public class Notifier
{
    public string Build(string target, int status)
    {
        var buffer = new StringBuilder();
        if (status == 0)
        {
            buffer.Append("empty");
        }
        else
        {
            buffer.Append(target);
        }
        for (int j = 0; j < status; j++)
        {
            buffer.Append("#");
        }
        return buffer.ToString();
    }
}
