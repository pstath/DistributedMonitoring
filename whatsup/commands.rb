require 'whatsup/urlcheck'

module Whatsup
  module Commands

    module CommandDefiner

      def all_cmds
        @@all_cmds ||= {}
      end

      def cmd(name, help, &block)
        all_cmds()[name.to_s] = help
        define_method(name, &block)
      end

    end

    class CommandProcessor

      extend CommandDefiner

      def initialize(conn)
        @jabber = conn
      end

      def dispatch(cmd, user, arg)
        if self.respond_to? cmd
          self.send cmd.to_sym, user, arg
        else
          send_msg user, "I don't understand #{cmd}.  Send `help' for what I do know."
        end
      end

      def send_msg(user, text)
        puts "Sending to #{user.jid}: #{text}"
        @jabber.deliver user.jid, text
      end

      cmd :help, "Get help for commands." do |user, arg|
        cmds = self.class.all_cmds()
        help_text = cmds.keys.sort.map {|k| "#{k}\t#{cmds[k]}"}
        send_msg user, help_text.join("\n")
      end

      cmd :get, "Get a URL" do |user, url|
        Whatsup::Urlcheck.fetch(url) do |res|
          send_msg user, "Got a #{res.status} from #{url} in #{res.time}s (#{res.body.size} bytes)"
        end
      end

      cmd :watch, "Watch a URL" do |user, url|
        Watch.create! :user => user, :url => url
      end

      cmd :on, "Enable all watches for you " do |user, nothing|
        user.update_attributes(:active => true)
        send_msg user, "Marked you active."
      end

      cmd :off, "Disable all watches for you" do |user, nothing|
        user.update_attributes(:active => false)
        send_msg user, "Marked you inactive."
      end

    end # CommandProcessor

  end
end