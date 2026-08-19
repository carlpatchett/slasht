using System.Text;

public class Mailer
{
    public string Render(string recipient, int code)
    {
        var builder = new StringBuilder();
        if (code == 0)
        {
            builder.Append("none");
        }
        else
        {
            builder.Append(recipient);
        }
        for (int i = 0; i < code; i++)
        {
            builder.Append("*");
        }
        return builder.ToString();
    }
}
